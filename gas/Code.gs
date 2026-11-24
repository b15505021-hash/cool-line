/**
 * COOL-LINE v7（開源雙雲端旗艦版・永久記憶金鑰・零重複零污染）
 * 核心修復：
 * 1. 金鑰雲端永久記憶（ScriptProperties）：重貼程式碼忘記填 Token 也不會再「已讀不回」！
 * 2. 雙雲端防衝突保護：當 GitHub Actions (Canvas API) 啟用時，GAS 不再用 .ics 把已繳交作業塞回清單
 * 3. 永久保留「完成」勾勾：在 LINE 手動打勾完成的項目，下次雲端同步不會被洗掉
 * 4. 點擊任一作業／考試標題，直接以手機外部瀏覽器（Safari/Chrome）開啟該作業繳交頁
 * 5. 防重複早報：若 07:55 GitHub Actions 已發送今日死線警報，08:00 GAS 不會重複推播第二次
 */

// ==================== 設定區（支援雲端自動記憶，貼過一次或跑過 cloud_sync 即永久保存） ====================
const CONFIG = {
  LINE_CHANNEL_ACCESS_TOKEN: '請填入您的_LINE_CHANNEL_ACCESS_TOKEN',
  LINE_USER_ID: '請填入您的_LINE_USER_ID',
  GEMINI_API_KEY: '請填入您的_GEMINI_API_KEY',
  // 選填：用來從 LINE 一鍵觸發 GitHub Actions 立即登入 COOL 爬蟲
  GITHUB_REPO: '請填入您的_GITHUB_REPO', // 格式：帳號/cool-line
  GITHUB_TOKEN: '請填入您的_GITHUB_PAT', // GitHub Fine-grained PAT (Actions: Read and write)
  // 選填：僅在未使用 GitHub Actions 時作為備援行事曆來源
  COOL_ICS_URL: '',
  GMAIL_LABEL_NAME: 'COOL-已通知',
};
// ==========================================================================================================

const PROP_NOTIFIED_KEY = 'COOL_NOTIFIED_IDS';
const PROP_TASKS_KEY = 'COOL_TASKS_LIST';
const PROP_PENDING_DATE_KEY = 'COOL_PENDING_PICKED_DATE';
const PROP_LAST_CANVAS_SYNC = 'COOL_LAST_CANVAS_SYNC_MS';
const MAX_STORED_IDS = 150;
const MAX_STORED_TASKS = 30;
const SAFE_PROP_BYTES = 7500;

/**
 * 智慧讀取金鑰：若程式碼內有填寫有效值，自動存入雲端屬性；若為預設範本字，自動從雲端屬性讀取！
 */
function getSecret_(key) {
  const props = PropertiesService.getScriptProperties();
  const propKey = 'CFG_' + key;
  const codeVal = (CONFIG[key] || '').trim();
  const isPlaceholder = !codeVal || codeVal.startsWith('請');

  if (!isPlaceholder) {
    if (props.getProperty(propKey) !== codeVal) {
      props.setProperty(propKey, codeVal);
    }
    return codeVal;
  }
  return (props.getProperty(propKey) || '').trim();
}

function hasRecentCanvasSync_() {
  const lastMs = Number(PropertiesService.getScriptProperties().getProperty(PROP_LAST_CANVAS_SYNC) || 0);
  // 36 小時內有跑過 GitHub Actions / cloud_sync.py 即視為雙雲端模式
  return lastMs > 0 && Date.now() - lastMs < 36 * 3600 * 1000;
}

/**
 * 排程 1（每 5 分鐘）：偵測 Gmail 即時新公告／突襲通知並推播
 */
function checkCoolUpdates() {
  const notifiedIds = loadNotifiedIds_();
  const tasks = loadTasks_();
  const canvasMode = hasRecentCanvasSync_();
  const alerts = [];
  const pendingGmailThreads = [];
  const newNotifiedIds = [];

  const label = getOrCreateLabel_(CONFIG.GMAIL_LABEL_NAME);
  const query = `from:ntu-cool@cool.ntu.edu.tw -label:"${CONFIG.GMAIL_LABEL_NAME}" newer_than:7d`;
  const threads = GmailApp.search(query, 0, 15);

  for (const thread of threads) {
    const messages = thread.getMessages();
    let threadHasAlert = false;

    for (const msg of messages) {
      const uid = `mail_${msg.getId()}`;
      if (notifiedIds.has(uid)) continue;

      const rawSubject = msg.getSubject() || 'NTU COOL 通知信';
      const cleanTitle = shortenTitle_(rawSubject);
      const plainBody = extractCleanBody_(msg);
      const summary = summarizeWithGemini_(rawSubject, plainBody);
      const category = classifyCategory_(rawSubject, plainBody);
      const parsedDue = extractDueDateFromText_(rawSubject + ' ' + plainBody);

      // 僅在未使用 Canvas API 同步時，才把信件猜測項目放進清單（避免污染精準清單）
      if (!canvasMode && (category === 'exam' || category === 'homework')) {
        upsertTask_(tasks, {
          id: uid,
          title: cleanTitle,
          category: category,
          dueMs: parsedDue ? parsedDue.dueMs : null,
          dueDisplay: parsedDue ? parsedDue.dueDisplay : '詳見信件',
          done: false,
          url: 'https://cool.ntu.edu.tw',
        });
      }

      alerts.push({
        category: category,
        type: getCategoryBadge_(category),
        title: cleanTitle,
        detail: summary,
        dueText: parsedDue ? parsedDue.dueDisplay : '',
      });

      newNotifiedIds.push(uid);
      threadHasAlert = true;
    }

    if (threadHasAlert) pendingGmailThreads.push(thread);
    else thread.addLabel(label);
  }

  // 僅在未使用 Canvas API 同步時，才啟用 .ics 備援（避免把已繳交作業塞回清單）
  const icsUrl = getSecret_('COOL_ICS_URL');
  if (!canvasMode && icsUrl && icsUrl.startsWith('http')) {
    const icsEvents = fetchUpcomingFromIcs_(icsUrl);
    for (const ev of icsEvents) {
      const uid = `ics_${ev.uid}`;
      const category = classifyCategory_(ev.summary, '');
      const cleanTitle = shortenTitle_(ev.summary);
      upsertTask_(tasks, {
        id: uid,
        title: cleanTitle,
        category: category,
        dueMs: ev.dueMs,
        dueDisplay: ev.dueDisplay,
        done: false,
        url: 'https://cool.ntu.edu.tw',
      });

      if (!notifiedIds.has(uid)) {
        alerts.push({
          category: category,
          type: getCategoryBadge_(category),
          title: cleanTitle,
          detail: '偵測到新行事曆任務（已同步至待辦清單）',
          dueText: ev.dueDisplay,
        });
        newNotifiedIds.push(uid);
      }
    }
  }

  if (!canvasMode) saveTasks_(tasks);

  if (alerts.length > 0) {
    const pushOk = pushMergedLineAlert_(alerts);
    if (pushOk) {
      for (const uid of newNotifiedIds) notifiedIds.add(uid);
      saveNotifiedIds_(notifiedIds);
      for (const thread of pendingGmailThreads) thread.addLabel(label);
    }
  } else {
    Logger.log('本次檢查無新動態。');
  }
}

/**
 * 排程 2（每天早上 8 點）：早安問候與備援提醒（自動避開與 GitHub Actions 重複推播）
 */
function sendDailyMorningBriefing() {
  const tasks = loadTasks_();
  const canvasMode = hasRecentCanvasSync_();
  if (!canvasMode) {
    syncIcsIntoTasks_(tasks);
    saveTasks_(tasks);
  }

  const now = new Date();
  const todayStr = Utilities.formatDate(now, 'Asia/Taipei', 'yyyy-MM-dd');
  const todayLabel = Utilities.formatDate(now, 'Asia/Taipei', 'MM/dd (EEE)');

  const dueToday = sortTasks_(tasks).filter((t) => {
    if (t.done || !t.dueMs) return false;
    return Utilities.formatDate(new Date(t.dueMs), 'Asia/Taipei', 'yyyy-MM-dd') === todayStr;
  });

  // 若今日有未繳交任務，且過去 2 小時內 GitHub Actions 剛跑過（已發過精準早報），則不重複推播第二次！
  const lastSyncMs = Number(PropertiesService.getScriptProperties().getProperty(PROP_LAST_CANVAS_SYNC) || 0);
  if (dueToday.length > 0 && lastSyncMs > 0 && Date.now() - lastSyncMs < 2 * 3600 * 1000) {
    Logger.log('GitHub Actions 剛發送過今日死線提醒，略過重複早報。');
    return;
  }

  let msgText = '';
  if (dueToday.length === 0) {
    msgText = `☀️ 早安！今天（${todayLabel}）沒有截止的未繳交作業或考試，祝你今天順心！`;
  } else {
    const hasExam = dueToday.some((t) => t.category === 'exam');
    const header = hasExam
      ? `❗❗❗ 早安緊急提醒：今天（${todayLabel}）有 ${dueToday.length} 項截止（含考試）❗❗❗`
      : `☀️ 早安！今天（${todayLabel}）有 ${dueToday.length} 項截止任務：`;

    const lines = dueToday.map((t, idx) => {
      const timeOnly = Utilities.formatDate(new Date(t.dueMs), 'Asia/Taipei', 'HH:mm');
      return `${idx + 1}. [${getCategoryBadge_(t.category)}] ${t.title}\n   ⏰ 今日 ${timeOnly} 截止`;
    });
    msgText = `${header}\n${'─'.repeat(18)}\n${lines.join('\n\n')}`;
  }

  pushLineMessages_([{ type: 'text', text: msgText, quickReply: buildQuickReplyBar_() }]);
}

function importPastCoolTasks(fastMode) {
  if (hasRecentCanvasSync_()) {
    // 雙雲端模式下，保護 Canvas API 同步的乾淨未繳交清單不被 Gmail 舊信覆蓋
    checkCoolUpdates();
    return 0;
  }

  const notifiedIds = loadNotifiedIds_();
  let tasks = loadTasks_().filter((t) => t.id.startsWith('man_') || t.done);

  const now = new Date();
  const todayStartMs = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0).getTime();

  let importedCount = 0;
  const limit = fastMode ? 20 : 35;
  const threads = GmailApp.search('from:ntu-cool@cool.ntu.edu.tw newer_than:30d', 0, limit);

  for (const thread of threads) {
    for (const msg of thread.getMessages()) {
      const uid = `mail_${msg.getId()}`;
      const rawSubject = msg.getSubject() || 'NTU COOL 通知信';
      const plainBody = extractCleanBody_(msg);
      const category = classifyCategory_(rawSubject, plainBody);
      const parsedDue = extractDueDateFromText_(rawSubject + ' ' + plainBody);
      const isExpired = parsedDue && parsedDue.dueMs < todayStartMs;

      if ((category === 'exam' || category === 'homework') && !isExpired) {
        const existed = tasks.some((t) => t.id === uid);
        upsertTask_(tasks, {
          id: uid,
          title: shortenTitle_(rawSubject),
          category: category,
          dueMs: parsedDue ? parsedDue.dueMs : null,
          dueDisplay: parsedDue ? parsedDue.dueDisplay : '詳見信件',
          done: false,
          url: 'https://cool.ntu.edu.tw',
        });
        if (!existed) importedCount++;
      }
      notifiedIds.add(uid);
    }
  }

  importedCount += syncIcsIntoTasks_(tasks);
  saveTasks_(tasks);
  saveNotifiedIds_(notifiedIds);
  return importedCount;
}

function testLinePush() {
  const ok = pushMergedLineAlert_([
    {
      category: 'exam',
      type: '⚡ 考試',
      title: '【緊急測試】微積分第 12 週突襲小考',
      detail: '📌 限時 10 分鐘作答｜⏰ 立即截止｜⚠️ 請馬上開啟 COOL',
      dueText: '今日 14:30',
    },
  ]);
  Logger.log(ok ? '測試推播成功！' : '測試推播失敗，請檢查執行紀錄。');
}

function doPost(e) {
  let lastReplyToken = '';
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput('OK');
    }
    const payload = JSON.parse(e.postData.contents);

    // 接收來自 GitHub Actions / cloud_sync.py 的真實「未繳交清單」與金鑰同步
    if (payload.sync_source === 'canvas_api' && payload.sync_secret) {
      const props = PropertiesService.getScriptProperties();
      const currentUserId = getSecret_('LINE_USER_ID');

      // 驗證身分（首次尚未設定 LINE_USER_ID 時允許自動綁定初始化）
      if (!currentUserId || currentUserId === payload.sync_secret) {
        if (!currentUserId) props.setProperty('CFG_LINE_USER_ID', String(payload.sync_secret).trim());
        if (payload.line_token) props.setProperty('CFG_LINE_CHANNEL_ACCESS_TOKEN', String(payload.line_token).trim());
        if (payload.gemini_key) props.setProperty('CFG_GEMINI_API_KEY', String(payload.gemini_key).trim());
        props.setProperty(PROP_LAST_CANVAS_SYNC, String(Date.now()));

        const prevTasks = loadTasks_();
        const doneIds = new Set(prevTasks.filter((t) => t.done).map((t) => t.id));
        const manualTasks = prevTasks.filter((t) => t.id.startsWith('man_'));

        const incoming = (Array.isArray(payload.tasks) ? payload.tasks : []).map((t) => ({
          id: t.id,
          title: t.title,
          category: t.category,
          dueMs: t.dueMs,
          dueDisplay: t.dueDisplay,
          done: Boolean(t.done || doneIds.has(t.id)),
          url: t.url || 'https://cool.ntu.edu.tw',
        }));

        saveTasks_(incoming.concat(manualTasks));
        return ContentService.createTextOutput('SYNC_OK');
      }
      return ContentService.createTextOutput('FORBIDDEN');
    }

    const events = payload.events || [];
    for (const event of events) {
      lastReplyToken = event.replyToken || '';
      if (event.type === 'postback' && event.postback && event.postback.data) {
        handlePostback_(event);
      } else if (event.type === 'message' && event.message && event.message.type === 'text') {
        handleTextMessage_(event);
      }
    }
  } catch (err) {
    Logger.log('doPost 錯誤：' + err);
    if (lastReplyToken) {
      replyRaw_(lastReplyToken, [
        {
          type: 'text',
          text: `⚠️ 系統剛剛遇到一點小狀況：${String(err).slice(0, 120)}\n請再試一次或點下方快捷鍵。`,
          quickReply: buildQuickReplyBar_(),
        },
      ]);
    }
  }
  return ContentService.createTextOutput('OK');
}

function handleTextMessage_(event) {
  const rawText = (event.message.text || '').trim();
  const lower = rawText.toLowerCase();
  const props = PropertiesService.getScriptProperties();

  const pendingIso = props.getProperty(PROP_PENDING_DATE_KEY);
  if (
    pendingIso &&
    !['清單', '作業', '考試', '日曆', '月曆', '同步', '新增', '取消'].includes(lower)
  ) {
    props.deleteProperty(PROP_PENDING_DATE_KEY);
    const dt = new Date(pendingIso);
    const dueDisplay = Utilities.formatDate(dt, 'Asia/Taipei', 'MM/dd (EEE) HH:mm');
    const category = classifyCategory_(rawText, '');
    const tasks = loadTasks_();
    tasks.push({
      id: `man_${Date.now()}`,
      title: shortenTitle_(rawText),
      category: category,
      dueMs: dt.getTime(),
      dueDisplay: dueDisplay,
      done: false,
      url: 'https://cool.ntu.edu.tw',
    });
    saveTasks_(tasks);

    replyDashboardSafe_(event.replyToken, tasks, 'all', `✅ 已加入【${getCategoryLabel_(category)}】：${shortenTitle_(rawText)}（⏰ ${dueDisplay}）`);
    return;
  }

  if (lower === '取消') {
    props.deleteProperty(PROP_PENDING_DATE_KEY);
    replyRaw_(event.replyToken, [
      { type: 'text', text: '已取消本次新增。', quickReply: buildQuickReplyBar_() },
    ]);
    return;
  }

  if (['爬蟲', '立即爬', '立即更新', '爬cool', '爬 cool'].some((kw) => lower.includes(kw))) {
    const res = triggerGithubCoolCrawler_();
    replyRaw_(event.replyToken, [
      { type: 'text', text: res.message, quickReply: buildQuickReplyBar_() },
    ]);
    return;
  }

  if (lower === '同步' || lower === 'sync') {
    if (hasRecentCanvasSync_()) {
      checkCoolUpdates();
      const tasks = loadTasks_();
      replyDashboardSafe_(
        event.replyToken,
        tasks,
        'all',
        '✅ 目前已啟用「NTU COOL 自動登入精準模式」（每天 07:55 與 23:00 自動過濾已繳交作業），並已剛掃描完最新信件：'
      );
      return;
    }

    const count = importPastCoolTasks(true);
    const tasks = loadTasks_();
    const ok = replyDashboardSafe_(
      event.replyToken,
      tasks,
      'all',
      `🔄 極速同步完成（新增 ${count} 筆）！左右滑動卡片可切換【全部／作業／考試／日曆】：`
    );
    if (!ok) {
      const fallback = buildDashboardCarousel_(tasks, 'all');
      fallback.quickReply = buildQuickReplyBar_();
      pushLineMessages_([
        { type: 'text', text: `🔄 同步完成（新增 ${count} 筆）：` },
        fallback,
      ]);
    }
    return;
  }

  if (lower === '日曆' || lower === '月曆' || lower === 'calendar') {
    const tasks = loadTasks_();
    const calFlex = {
      type: 'flex',
      altText: 'COOL-LINE 本月月曆',
      contents: buildCalendarBubble_(tasks, new Date()),
      quickReply: buildQuickReplyBar_(),
    };
    const ok = replyRaw_(event.replyToken, [calFlex]);
    if (!ok) {
      replyRaw_(event.replyToken, [
        { type: 'text', text: buildPlainTextSummary_(tasks), quickReply: buildQuickReplyBar_() },
      ]);
    }
    return;
  }

  if (rawText.startsWith('新增') || rawText.startsWith('+')) {
    const body = rawText.replace(/^(新增|\+)\s*/, '').trim();
    if (!body) {
      const calFlex = {
        type: 'flex',
        altText: '選日期新增待辦',
        contents: buildCalendarBubble_(loadTasks_(), new Date()),
        quickReply: buildQuickReplyBar_(),
      };
      replyRaw_(event.replyToken, [
        { type: 'text', text: '點下方「📅 選日期新增待辦」，或直接打「新增 11/28 14:00 微積分小考」：' },
        calFlex,
      ]);
      return;
    }

    const parsed = parseManualTaskInput_(body);
    const tasks = loadTasks_();
    tasks.push({
      id: `man_${Date.now()}`,
      title: shortenTitle_(parsed.title),
      category: parsed.category,
      dueMs: parsed.dueMs,
      dueDisplay: parsed.dueDisplay,
      done: false,
      url: 'https://cool.ntu.edu.tw',
    });
    saveTasks_(tasks);

    replyDashboardSafe_(
      event.replyToken,
      tasks,
      'all',
      `✅ 已新增至【${getCategoryLabel_(parsed.category)}】：${shortenTitle_(parsed.title)}（⏰ ${parsed.dueDisplay}）`
    );
    return;
  }

  if (['清單', '作業', '考試', '行事曆', 'check', 'todo', '全部'].some((kw) => lower.includes(kw))) {
    const tasks = loadTasks_();
    let firstTab = 'all';
    if (lower === '作業') firstTab = 'homework';
    else if (lower === '考試') firstTab = 'exam';

    replyDashboardSafe_(event.replyToken, tasks, firstTab, '');
    return;
  }

  replyRaw_(event.replyToken, [
    {
      type: 'text',
      text:
        '👋 我是 COOL-LINE 課程助理！直接點下方快捷鍵即可：\n' +
        '📋 「清單」→ 左右滑動看【全部／作業／考試／日曆】（點標題直達 COOL）\n' +
        '📅 「日曆」→ 單看本月死線月曆\n' +
        '➕ 「新增 11/28 14:00 微積分小考」→ 手動建待辦',
      quickReply: buildQuickReplyBar_(),
    },
  ]);
}

function handlePostback_(event) {
  const params = parseQuery_(event.postback.data);
  const action = params.action || '';
  const taskId = params.id || '';

  if (action === 'pick_date' && event.postback.params && event.postback.params.datetime) {
    const dt = new Date(event.postback.params.datetime + ':00+08:00');
    PropertiesService.getScriptProperties().setProperty(PROP_PENDING_DATE_KEY, dt.toISOString());
    const display = Utilities.formatDate(dt, 'Asia/Taipei', 'MM/dd (EEE) HH:mm');
    replyRaw_(event.replyToken, [
      {
        type: 'text',
        text: `📅 已選時間：${display}\n請直接輸入「事項名稱」（例如：微積分小考），輸入「取消」可放棄。`,
        quickReply: buildQuickReplyBar_(),
      },
    ]);
    return;
  }

  if (action === 'show_cal') {
    const y = Number(params.y), m = Number(params.m);
    const baseDate = y && !isNaN(m) ? new Date(y, m, 1) : new Date();
    const calFlex = {
      type: 'flex',
      altText: 'COOL-LINE 月曆',
      contents: buildCalendarBubble_(loadTasks_(), baseDate),
      quickReply: buildQuickReplyBar_(),
    };
    replyRaw_(event.replyToken, [calFlex]);
    return;
  }

  let tasks = loadTasks_();
  if (action === 'toggle' && taskId) {
    for (const t of tasks) {
      if (t.id === taskId) {
        t.done = !t.done;
        break;
      }
    }
    saveTasks_(tasks);
  } else if (action === 'clear_done') {
    tasks = tasks.filter((t) => !t.done);
    saveTasks_(tasks);
  }

  replyDashboardSafe_(event.replyToken, tasks, 'all', '');
}

function replyDashboardSafe_(replyToken, tasks, firstTab, prefixText) {
  const carousel = buildDashboardCarousel_(tasks, firstTab);
  carousel.quickReply = buildQuickReplyBar_();
  const msgs = prefixText ? [{ type: 'text', text: prefixText }, carousel] : [carousel];

  if (replyRaw_(replyToken, msgs)) return true;

  const fallbackText = (prefixText ? prefixText + '\n\n' : '') + buildPlainTextSummary_(tasks);
  return replyRaw_(replyToken, [
    { type: 'text', text: fallbackText, quickReply: buildQuickReplyBar_() },
  ]);
}

function buildPlainTextSummary_(tasks) {
  const pending = sortTasks_(tasks).filter((t) => !t.done);
  if (pending.length === 0) return '🎉 目前沒有未完成的待辦任務！';
  const lines = pending.slice(0, 12).map((t, i) => {
    return `${i + 1}. [${getCategoryBadge_(t.category)}] ${t.title}（⏰ ${t.dueDisplay || '詳見信件'}）`;
  });
  return `📋 未完成待辦（共 ${pending.length} 項）：\n` + lines.join('\n');
}

function buildQuickReplyBar_() {
  return {
    items: [
      { type: 'action', action: { type: 'message', label: '📋 滑動總覽', text: '清單' } },
      { type: 'action', action: { type: 'message', label: '🚀 立即爬 COOL', text: '立即爬' } },
      { type: 'action', action: { type: 'message', label: '📅 本月日曆', text: '日曆' } },
      { type: 'action', action: { type: 'message', label: '📝 只看作業', text: '作業' } },
      { type: 'action', action: { type: 'message', label: '⚡ 只看考試', text: '考試' } },
    ],
  };
}

function triggerGithubCoolCrawler_() {
  const repo = getSecret_('GITHUB_REPO');
  const ghToken = getSecret_('GITHUB_TOKEN');
  if (!repo || !ghToken) {
    return {
      ok: false,
      message: '⚠️ 尚未設定 GITHUB_REPO 或 GITHUB_TOKEN，無法從 LINE 遠端觸發雲端爬蟲。',
    };
  }
  const url = `https://api.github.com/repos/${repo}/actions/workflows/daily_cool.yml/dispatches`;
  try {
    const res = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: `Bearer ${ghToken}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      payload: JSON.stringify({ ref: 'main' }),
      muteHttpExceptions: true,
    });
    const code = res.getResponseCode();
    if (code === 204) {
      return {
        ok: true,
        message: '🚀 已啟動雲端爬蟲登入 NTU COOL！\n約 45～60 秒後會自動更新您的未繳交清單並通知您，屆時點「📋 滑動總覽」即可看到最新狀態！',
      };
    }
    return {
      ok: false,
      message: `⚠️ 觸發 GitHub 爬蟲失敗（HTTP ${code}），請檢查 GITHUB_TOKEN 權限（需開啟 Actions: Read and write）。`,
    };
  } catch (err) {
    return { ok: false, message: `⚠️ 觸發失敗：${String(err).slice(0, 100)}` };
  }
}

function buildDashboardCarousel_(tasks, firstTab) {
  const order = ['all', 'homework', 'exam', 'calendar'];
  if (firstTab && order.includes(firstTab) && firstTab !== 'all') {
    const rest = order.filter((x) => x !== firstTab);
    order.splice(0, order.length, firstTab, ...rest);
  }

  const bubbles = order.map((tab) =>
    tab === 'calendar' ? buildCalendarBubble_(tasks, new Date()) : buildChecklistBubble_(tasks, tab)
  );

  return {
    type: 'flex',
    altText: 'COOL-LINE 儀表板（左右滑動切換：全部／作業／考試／日曆）',
    contents: { type: 'carousel', contents: bubbles },
  };
}

function buildChecklistBubble_(tasks, filter) {
  const sorted = sortTasks_(tasks);
  const filtered =
    filter && filter !== 'all' ? sorted.filter((t) => t.category === filter) : sorted;

  const pendingList = filtered.filter((t) => !t.done);
  const doneList = filtered.filter((t) => t.done);
  const displayItems = pendingList.concat(doneList).slice(0, 6);

  const headerMap = {
    all: { title: '📋 全部待辦（點標題開 COOL 👉）', bg: '#1E3A8A' },
    homework: { title: '📝 作業／報告清單', bg: '#2563EB' },
    exam: { title: '⚡ 考試／小考清單', bg: '#D97706' },
  };
  const h = headerMap[filter] || headerMap.all;

  const bodyContents = [];
  if (displayItems.length === 0) {
    bodyContents.push({
      type: 'text',
      text: '🎉 此分類目前沒有待辦任務！\n點下方「📅 選日期新增」或往右滑看月曆。',
      wrap: true,
      size: 'sm',
      color: '#4A5568',
      margin: 'md',
    });
  } else {
    displayItems.forEach((item, idx) => {
      if (idx > 0) bodyContents.push({ type: 'separator', margin: 'sm' });

      const statusIcon = item.done ? '✅' : '⬜';
      const titleColor = item.done ? '#9CA3AF' : '#1A202C';
      const btnLabel = item.done ? '復原' : '完成';
      const btnStyle = item.done ? 'secondary' : 'primary';
      const btnColor = item.done ? '#E5E7EB' : '#10B981';

      bodyContents.push({
        type: 'box',
        layout: 'horizontal',
        margin: 'sm',
        spacing: 'sm',
        alignItems: 'center',
        contents: [
          {
            type: 'box',
            layout: 'vertical',
            flex: 4,
            action: {
              type: 'uri',
              label: '開啟 COOL',
              uri: buildExternalUrl_(item.url),
            },
            contents: [
              {
                type: 'text',
                text: `${statusIcon} ${item.title || '未命名事項'}`,
                size: 'sm',
                weight: item.done ? 'regular' : 'bold',
                color: titleColor,
                wrap: true,
                maxLines: 2,
                decoration: item.done ? 'line-through' : 'none',
              },
              {
                type: 'text',
                text: `${getCategoryBadge_(item.category)} ｜ ⏰ ${item.dueDisplay || '詳見信件'}`,
                size: 'xxs',
                color: item.done ? '#9CA3AF' : '#DC2626',
                wrap: true,
                margin: 'xs',
              },
            ],
          },
          {
            type: 'button',
            flex: 0,
            height: 'sm',
            style: btnStyle,
            color: btnColor,
            action: {
              type: 'postback',
              label: btnLabel,
              data: `action=toggle&id=${encodeURIComponent(item.id)}`,
            },
          },
        ],
      });
    });
  }

  const footerContents = [
    {
      type: 'button',
      style: 'primary',
      color: '#2563EB',
      height: 'sm',
      action: {
        type: 'datetimepicker',
        label: '📅 選日期新增待辦',
        data: 'action=pick_date',
        mode: 'datetime',
      },
    },
  ];
  if (doneList.length > 0) {
    footerContents.push({
      type: 'button',
      style: 'secondary',
      height: 'sm',
      margin: 'sm',
      action: {
        type: 'postback',
        label: `🗑️ 清除已完成 (${doneList.length})`,
        data: 'action=clear_done',
      },
    });
  }

  return {
    type: 'bubble',
    size: 'mega',
    header: {
      type: 'box',
      layout: 'vertical',
      backgroundColor: h.bg,
      paddingAll: '12px',
      contents: [
        { type: 'text', text: h.title, weight: 'bold', size: 'sm', color: '#FFFFFF', wrap: true },
        {
          type: 'text',
          text: `未完成 ${pendingList.length} 項 ｜ 已完成 ${doneList.length} 項`,
          size: 'xs',
          color: '#E0E7FF',
          margin: 'xs',
        },
      ],
    },
    body: { type: 'box', layout: 'vertical', paddingAll: '12px', contents: bodyContents },
    footer: { type: 'box', layout: 'vertical', paddingAll: '10px', contents: footerContents },
  };
}

function buildCalendarBubble_(tasks, targetDate) {
  const year = targetDate.getFullYear();
  const month = targetDate.getMonth();
  const startWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const dayMarkers = {};
  const monthTasks = [];
  for (const t of sortTasks_(tasks)) {
    if (t.done || !t.dueMs) continue;
    const d = new Date(t.dueMs);
    if (d.getFullYear() === year && d.getMonth() === month) {
      const dayNum = d.getDate();
      if (!dayMarkers[dayNum] || t.category === 'exam') dayMarkers[dayNum] = t.category;
      monthTasks.push(t);
    }
  }

  const rows = [
    {
      type: 'box',
      layout: 'horizontal',
      contents: ['日', '一', '二', '三', '四', '五', '六'].map((w, idx) => ({
        type: 'text',
        text: w,
        align: 'center',
        size: 'xs',
        weight: 'bold',
        color: idx === 0 || idx === 6 ? '#EF4444' : '#6B7280',
        flex: 1,
      })),
    },
    { type: 'separator', margin: 'xs' },
  ];

  let cells = [];
  for (let i = 0; i < startWeekday; i++) {
    cells.push({ type: 'text', text: '·', flex: 1, size: 'xs', align: 'center', color: '#FFFFFF' });
  }
  for (let day = 1; day <= daysInMonth; day++) {
    const marker = dayMarkers[day];
    let bg = '#FFFFFF', fg = '#1F2937';
    if (marker === 'exam') { bg = '#FEE2E2'; fg = '#DC2626'; }
    else if (marker === 'homework') { bg = '#DBEAFE'; fg = '#1D4ED8'; }

    cells.push({
      type: 'box',
      layout: 'vertical',
      flex: 1,
      backgroundColor: bg,
      cornerRadius: '4px',
      paddingAll: '2px',
      contents: [
        {
          type: 'text',
          text: String(day),
          align: 'center',
          size: 'xs',
          weight: marker ? 'bold' : 'regular',
          color: fg,
        },
      ],
    });
    if (cells.length === 7) {
      rows.push({ type: 'box', layout: 'horizontal', margin: 'xs', contents: cells });
      cells = [];
    }
  }
  if (cells.length > 0) {
    while (cells.length < 7) {
      cells.push({ type: 'text', text: '·', flex: 1, size: 'xs', align: 'center', color: '#FFFFFF' });
    }
    rows.push({ type: 'box', layout: 'horizontal', margin: 'xs', contents: cells });
  }

  rows.push({ type: 'separator', margin: 'sm' });
  rows.push({
    type: 'text',
    text: '🔴 紅底＝考試　🔵 藍底＝作業',
    size: 'xxs',
    color: '#6B7280',
    align: 'center',
    margin: 'xs',
  });

  if (monthTasks.length > 0) {
    monthTasks.slice(0, 8).forEach((t) => {
      rows.push({
        type: 'text',
        text: `• ${t.dueDisplay}｜${t.title}`,
        size: 'xs',
        color: t.category === 'exam' ? '#DC2626' : '#1F2937',
        wrap: true,
        margin: 'xs',
      });
    });
  } else {
    rows.push({
      type: 'text',
      text: '本月目前沒有尚未繳交的死線任務！',
      size: 'xs',
      color: '#6B7280',
      wrap: true,
      margin: 'xs',
    });
  }

  const prevM = month === 0 ? 11 : month - 1, prevY = month === 0 ? year - 1 : year;
  const nextM = month === 11 ? 0 : month + 1, nextY = month === 11 ? year + 1 : year;

  return {
    type: 'bubble',
    size: 'mega',
    header: {
      type: 'box',
      layout: 'horizontal',
      backgroundColor: '#0F766E',
      paddingAll: '12px',
      alignItems: 'center',
      contents: [
        {
          type: 'button',
          flex: 0,
          height: 'sm',
          style: 'secondary',
          action: { type: 'postback', label: '◀', data: `action=show_cal&y=${prevY}&m=${prevM}` },
        },
        {
          type: 'text',
          text: `📅 ${year} 年 ${month + 1} 月`,
          weight: 'bold',
          size: 'md',
          color: '#FFFFFF',
          align: 'center',
          flex: 1,
        },
        {
          type: 'button',
          flex: 0,
          height: 'sm',
          style: 'secondary',
          action: { type: 'postback', label: '▶', data: `action=show_cal&y=${nextY}&m=${nextM}` },
        },
      ],
    },
    body: { type: 'box', layout: 'vertical', paddingAll: '12px', contents: rows },
    footer: {
      type: 'box',
      layout: 'vertical',
      paddingAll: '10px',
      contents: [
        {
          type: 'button',
          style: 'primary',
          color: '#10B981',
          height: 'sm',
          action: {
            type: 'datetimepicker',
            label: '📅 選日期新增待辦',
            data: 'action=pick_date',
            mode: 'datetime',
          },
        },
      ],
    },
  };
}

function buildExternalUrl_(rawUrl) {
  const base = rawUrl && String(rawUrl).startsWith('http') ? String(rawUrl) : 'https://cool.ntu.edu.tw';
  if (base.includes('openExternalBrowser=1')) return base;
  return base + (base.includes('?') ? '&' : '?') + 'openExternalBrowser=1';
}

function shortenTitle_(raw) {
  let s = (raw || '未命名事項').replace(/\s+/g, ' ').trim();
  s = s.replace(/^(作業截止日期已更改|作業已建立|作業已更改|近期\s*NTU COOL\s*通知)\s*[：:\-]\s*/i, '');
  if (s.length > 36) s = s.slice(0, 35) + '…';
  return s || '未命名事項';
}

function classifyCategory_(subject, body) {
  const subj = (subject || '').toLowerCase();
  if (/(已發佈的提交項目|最終分數|分數已更改|成績|閱卷|近期\s*ntu\s*cool\s*通知|graded|grade\s*posted)/.test(subj)) {
    return 'notice';
  }
  if (/(quiz|exam|midterm|小考|期中考|期末考|隨堂考|測驗|考試)/.test(subj)) {
    return 'exam';
  }
  const s = (subj + ' ' + (body || '').slice(0, 120)).toLowerCase();
  if (/(assignment|homework|hw\d*|lab|report|作業|報告|繳交|表單|填寫|分組)/.test(s)) {
    return 'homework';
  }
  return 'notice';
}

function extractDueDateFromText_(text) {
  if (!text) return null;
  const curYear = new Date().getFullYear();
  const m1 = text.match(/(?:(\d{4})[\/\-年])?(\d{1,2})[\/月](\d{1,2})日?(?:\s*(?:晚上|下午)?\s*(\d{1,2}):(\d{2}))?/);
  if (m1) {
    const year = m1[1] ? Number(m1[1]) : curYear;
    const month = Number(m1[2]), day = Number(m1[3]);
    if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
      const dt = new Date(year, month - 1, day, m1[4] ? Number(m1[4]) : 23, m1[5] ? Number(m1[5]) : 59, 0);
      return {
        dueMs: dt.getTime(),
        dueDisplay: Utilities.formatDate(dt, 'Asia/Taipei', 'MM/dd (EEE) HH:mm'),
      };
    }
  }
  return null;
}

function getCategoryBadge_(category) {
  if (category === 'exam') return '⚡ 考試';
  if (category === 'homework') return '📝 作業';
  return '📢 公告';
}

function getCategoryLabel_(category) {
  if (category === 'exam') return '⚡ 考試／小考';
  if (category === 'homework') return '📝 作業／報告';
  return '📢 公告／其他';
}

function parseManualTaskInput_(text) {
  const now = new Date();
  let dueMs = null, dueDisplay = '未指定時間', title = text;
  const m = text.match(/^(?:(\d{4})[\/\-])?(\d{1,2})[\/\-](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?\s+(.+)$/);
  if (m) {
    const dt = new Date(m[1] ? Number(m[1]) : now.getFullYear(), Number(m[2]) - 1, Number(m[3]), m[4] ? Number(m[4]) : 23, m[5] ? Number(m[5]) : 59, 0);
    dueMs = dt.getTime();
    dueDisplay = Utilities.formatDate(dt, 'Asia/Taipei', 'MM/dd (EEE) HH:mm');
    title = m[6].trim();
  }
  return { title: title, category: classifyCategory_(title, ''), dueMs: dueMs, dueDisplay: dueDisplay };
}

function syncIcsIntoTasks_(tasks) {
  const icsUrl = getSecret_('COOL_ICS_URL');
  if (!icsUrl || !icsUrl.startsWith('http')) return 0;
  let added = 0;
  const icsEvents = fetchUpcomingFromIcs_(icsUrl);
  for (const ev of icsEvents) {
    const uid = `ics_${ev.uid}`;
    if (!tasks.some((t) => t.id === uid)) added++;
    upsertTask_(tasks, {
      id: uid,
      title: shortenTitle_(ev.summary),
      category: classifyCategory_(ev.summary, ''),
      dueMs: ev.dueMs,
      dueDisplay: ev.dueDisplay,
      done: false,
      url: 'https://cool.ntu.edu.tw',
    });
  }
  return added;
}

function extractCleanBody_(msg) {
  let text = msg.getPlainBody() || '';
  if (!text.trim()) {
    text = (msg.getBody() || '')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/gi, ' ')
      .replace(/&amp;/gi, '&');
  }
  return text.replace(/\s+/g, ' ').trim();
}

function summarizeWithGemini_(subject, body) {
  const fallback = () => `📌 ${(body || subject).slice(0, 90)}${body.length > 90 ? '...' : ''}`;
  const geminiKey = getSecret_('GEMINI_API_KEY');
  if (!geminiKey) return fallback();

  const prompt =
    '你是台大 NTU COOL 課程助理。請將以下課程通知信濃縮為「不超過 60 個繁體中文字」的重點。\n' +
    '規則：只准根據原文中明確出現的資訊回答，原文沒寫的時間請填「無」，嚴禁自行推測或編造。\n' +
    '格式：📌 重點摘要｜⏰ 截止/考試時間｜⚠️ 注意事項\n\n' +
    `主旨：${subject}\n內文：${body.slice(0, 1800)}`;

  const url =
    'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' +
    encodeURIComponent(geminiKey);
  try {
    const res = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }),
      muteHttpExceptions: true,
    });
    if (res.getResponseCode() !== 200) return fallback();
    const data = JSON.parse(res.getContentText());
    const text = data.candidates && data.candidates[0] && data.candidates[0].content &&
      data.candidates[0].content.parts && data.candidates[0].content.parts[0] &&
      data.candidates[0].content.parts[0].text;
    return text ? text.replace(/\s+/g, ' ').trim() : fallback();
  } catch (err) {
    return fallback();
  }
}

function fetchUpcomingFromIcs_(icsUrl) {
  try {
    const res = UrlFetchApp.fetch(icsUrl, { muteHttpExceptions: true });
    if (res.getResponseCode() !== 200) return [];
    const raw = res.getContentText().replace(/\r\n[ \t]/g, '').replace(/\n[ \t]/g, '');
    const blocks = raw.split('BEGIN:VEVENT').slice(1);
    const now = new Date();
    const upcoming = [];
    for (const block of blocks) {
      const endIdx = block.indexOf('END:VEVENT');
      const content = endIdx !== -1 ? block.slice(0, endIdx) : block;
      const uidMatch = content.match(/^UID:(.*)$/m);
      const summaryMatch = content.match(/^SUMMARY(?:;[^:]*)?:(.*)$/m);
      const dtMatch = content.match(/^DTSTART(?:;[^:]*)?:(.*)$/m);
      if (!uidMatch || !summaryMatch || !dtMatch) continue;
      const dueDate = parseIcsDate_(dtMatch[1].trim());
      if (!dueDate || dueDate < now) continue;
      upcoming.push({
        uid: uidMatch[1].trim(),
        summary: summaryMatch[1].trim().replace(/\\,/g, ',').replace(/\\n/g, ' '),
        dueMs: dueDate.getTime(),
        dueDisplay: Utilities.formatDate(dueDate, 'Asia/Taipei', 'MM/dd (EEE) HH:mm'),
      });
    }
    upcoming.sort((a, b) => a.dueMs - b.dueMs);
    return upcoming;
  } catch (err) {
    return [];
  }
}

function parseIcsDate_(val) {
  const m = val.match(/^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?$/);
  if (!m) return null;
  return m[7] === 'Z'
    ? new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4] || 23), Number(m[5] || 59), Number(m[6] || 0)))
    : new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4] || 23), Number(m[5] || 59), Number(m[6] || 0));
}

function pushMergedLineAlert_(alerts) {
  const hasExam = alerts.some((item) => item.category === 'exam');
  let header = `🚨 NTU COOL 偵測到 ${alerts.length} 筆新動態！\n${'─'.repeat(18)}`;
  if (hasExam) {
    header =
      '❗❗❗❗❗❗❗❗❗❗\n' +
      '🚨‼️【緊急考試通知】‼️🚨\n' +
      `❗❗ 偵測到 ${alerts.length} 筆新動態（含考試）❗❗\n` +
      '❗❗❗❗❗❗❗❗❗❗';
  }
  const blocks = alerts.map((item, idx) => {
    const prefix = item.category === 'exam' ? '❗❗❗ ' : '';
    const suffix = item.category === 'exam' ? ' ❗❗❗' : '';
    const lines = [`${idx + 1}. ${prefix}[${item.type}] ${item.title}${suffix}`];
    if (item.dueText) lines.push(`   ⏰ 期限：${item.dueText}`);
    if (item.detail) lines.push(`   ${item.detail}`);
    return lines.join('\n');
  });

  let text = `${header}\n\n${blocks.join('\n\n')}`;
  if (text.length > 4800) text = text.slice(0, 4780) + '\n\n...（其餘請至 COOL 查看）';

  return pushLineMessages_([{ type: 'text', text: text, quickReply: buildQuickReplyBar_() }]);
}

function pushLineMessages_(messages) {
  const token = getSecret_('LINE_CHANNEL_ACCESS_TOKEN');
  const userId = getSecret_('LINE_USER_ID');
  if (!token || !userId) {
    Logger.log('尚未設定 LINE Token 或 User ID。');
    return false;
  }
  const res = UrlFetchApp.fetch('https://api.line.me/v2/bot/message/push', {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: `Bearer ${token}` },
    payload: JSON.stringify({ to: userId, messages: messages }),
    muteHttpExceptions: true,
  });
  if (res.getResponseCode() !== 200) Logger.log('LINE Push 失敗：' + res.getContentText());
  return res.getResponseCode() === 200;
}

function replyRaw_(replyToken, messages) {
  const token = getSecret_('LINE_CHANNEL_ACCESS_TOKEN');
  if (!token) {
    Logger.log('尚未設定 LINE_CHANNEL_ACCESS_TOKEN，無法 Reply。');
    return false;
  }
  const res = UrlFetchApp.fetch('https://api.line.me/v2/bot/message/reply', {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: `Bearer ${token}` },
    payload: JSON.stringify({ replyToken: replyToken, messages: messages }),
    muteHttpExceptions: true,
  });
  if (res.getResponseCode() !== 200) {
    Logger.log('LINE Reply 失敗 (' + res.getResponseCode() + ')：' + res.getContentText());
  }
  return res.getResponseCode() === 200;
}

function parseQuery_(queryStr) {
  const result = {};
  if (!queryStr) return result;
  queryStr.split('&').forEach((pair) => {
    const idx = pair.indexOf('=');
    if (idx === -1) return;
    result[decodeURIComponent(pair.slice(0, idx))] = decodeURIComponent(pair.slice(idx + 1));
  });
  return result;
}

function upsertTask_(tasks, newTask) {
  const existing = tasks.find((t) => t.id === newTask.id);
  if (existing) {
    existing.title = newTask.title;
    existing.category = newTask.category;
    if (newTask.url) existing.url = newTask.url;
    if (newTask.dueMs) {
      existing.dueMs = newTask.dueMs;
      existing.dueDisplay = newTask.dueDisplay;
    }
  } else {
    tasks.push(newTask);
  }
}

function sortTasks_(tasks) {
  return tasks.slice().sort((a, b) => {
    if (a.done !== b.done) return a.done ? 1 : -1;
    return (a.dueMs || 9999999999999) - (b.dueMs || 9999999999999);
  });
}

function loadTasks_() {
  const raw = PropertiesService.getScriptProperties().getProperty(PROP_TASKS_KEY);
  if (!raw) return [];
  try { return JSON.parse(raw); } catch (e) { return []; }
}

function saveTasks_(tasks) {
  let list = sortTasks_(tasks).slice(0, MAX_STORED_TASKS);
  let json = JSON.stringify(list);
  while (list.length > 0 && Utilities.newBlob(json).getBytes().length > SAFE_PROP_BYTES) {
    list.pop();
    json = JSON.stringify(list);
  }
  PropertiesService.getScriptProperties().setProperty(PROP_TASKS_KEY, json);
}

function getOrCreateLabel_(name) {
  let label = GmailApp.getUserLabelByName(name);
  if (!label) label = GmailApp.createLabel(name);
  return label;
}

function loadNotifiedIds_() {
  const raw = PropertiesService.getScriptProperties().getProperty(PROP_NOTIFIED_KEY);
  if (!raw) return new Set();
  try { return new Set(JSON.parse(raw)); } catch (e) { return new Set(); }
}

function saveNotifiedIds_(idSet) {
  let arr = Array.from(idSet).slice(-MAX_STORED_IDS);
  let json = JSON.stringify(arr);
  while (arr.length > 0 && Utilities.newBlob(json).getBytes().length > SAFE_PROP_BYTES) {
    arr.shift();
    json = JSON.stringify(arr);
  }
  PropertiesService.getScriptProperties().setProperty(PROP_NOTIFIED_KEY, json);
}
