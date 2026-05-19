// Background service worker
// TalentScreen - Whitebox Learning Autofill Extension v2.0
importScripts('/src/core/resumeProcessor.js');

try {
  if (chrome.sidePanel && chrome.sidePanel.setPanelBehavior) {
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }, () => {
      if (chrome.runtime.lastError) {
        console.error("SidePanel behavior error (ignorable):", chrome.runtime.lastError);
      }
    });
  }
} catch (e) {
  console.warn("SidePanel API not fully supported or error during init:", e);
}

// Track open side panels per window
const openSidePanelWindows = new Set();

chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "sidepanel") {
    let windowId = null;

    port.onMessage.addListener((msg) => {
      if (msg.action === 'register_window' && msg.windowId) {
        windowId = msg.windowId;
        openSidePanelWindows.add(windowId);
      }
    });

    port.onDisconnect.addListener(() => {
      if (windowId) {
        openSidePanelWindows.delete(windowId);
      }
    });
  }
});

// Helper function to check if URL is an ATS site
function isATSSite(url) {
  if (!url) return false;
  const urlLower = url.toLowerCase();
  const jobBoards = [
    'greenhouse.io', 'lever.co', 'myworkdayjobs.com', 'workday.com',
    'smartrecruiters.com', 'applytojob.com', 'ashbyhq.com', 'bamboohr.com',
    'icims.com', 'indeed.com', 'linkedin.com/jobs', 'workable.com',
    'taleo.net', 'successfactors.com', 'personio.com', 'recruitee.com',
    'teamtailor.com', 'ultipro.com', 'ukg.com', 'paycomonline.net',
    'paychex.com', 'oraclecloud.com', 'brassring.com', 'adp.com',
    'jobvite.com', 'rippling-ats.com'
  ];
  return jobBoards.some(board => urlLower.includes(board));
}

// Helper function to try opening side panel with retry
async function tryOpenSidePanel(tabId, windowId, retryCount = 0) {
  const maxRetries = 3;

  if (openSidePanelWindows.has(windowId)) {
    console.log('[TalentScreen] Side panel already open for this window');
    return true;
  }

  try {
    await chrome.sidePanel.open({ tabId });
    console.log(`[TalentScreen] Successfully opened side panel for tab ${tabId}`);
    return true;
  } catch (error) {
    if (retryCount < maxRetries) {
      // Retry after a short delay
      setTimeout(() => {
        tryOpenSidePanel(tabId, windowId, retryCount + 1);
      }, 500 * (retryCount + 1)); // Exponential backoff: 500ms, 1000ms, 1500ms
      console.log(`[TalentScreen] Retry ${retryCount + 1}/${maxRetries} to open side panel`);
    } else {
      console.log('[TalentScreen] Side panel requires user interaction to open');
    }
    return false;
  }
}

// Auto-open side panel on job sites
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    const isJobSite = isATSSite(tab.url);

    if (isJobSite) {
      // Show badge to indicate ATS site detected
      chrome.action.setBadgeText({ text: '!', tabId });
      chrome.action.setBadgeBackgroundColor({ color: '#4CAF50', tabId });
      chrome.action.setTitle({ title: 'Click to open TalentScreen autofill', tabId });

      // Store that we detected a job site
      chrome.storage.session?.set({ lastJobSiteDetected: { url: tab.url, tabId, windowId: tab.windowId } }).catch(() => {});

      // Try to auto-open side panel
      await tryOpenSidePanel(tabId, tab.windowId);
    } else {
      // Clear badge on non-ATS sites
      chrome.action.setBadgeText({ text: '', tabId });
      chrome.action.setTitle({ title: 'Open side panel', tabId });
    }
  }
});

// Also handle tab activation (switching between tabs)
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  const tab = await chrome.tabs.get(activeInfo.tabId);
  if (tab.url) {
    const isJobSite = isATSSite(tab.url);

    if (isJobSite) {
      chrome.action.setBadgeText({ text: '!', tabId: activeInfo.tabId });
      chrome.action.setBadgeBackgroundColor({ color: '#4CAF50', tabId: activeInfo.tabId });
      chrome.action.setTitle({ title: 'Click to open TalentScreen autofill', tabId: activeInfo.tabId });

      // Try to auto-open side panel when switching to ATS tab
      await tryOpenSidePanel(activeInfo.tabId, activeInfo.windowId);
    } else {
      chrome.action.setBadgeText({ text: '', tabId: activeInfo.tabId });
      chrome.action.setTitle({ title: 'Open side panel', tabId: activeInfo.tabId });
    }
  }
});

// Handle new windows opened with ATS sites
chrome.windows.onCreated.addListener(async (window) => {
  // Wait a moment for tabs to load
  setTimeout(async () => {
    try {
      const tabs = await chrome.tabs.query({ windowId: window.id });
      const activeTab = tabs.find(tab => tab.active);

      if (activeTab && activeTab.url && isATSSite(activeTab.url)) {
        console.log('[TalentScreen] New window opened with ATS site, attempting to open side panel');

        // Show badge
        chrome.action.setBadgeText({ text: '!', tabId: activeTab.id });
        chrome.action.setBadgeBackgroundColor({ color: '#4CAF50', tabId: activeTab.id });
        chrome.action.setTitle({ title: 'Click to open TalentScreen autofill', tabId: activeTab.id });

        // Try to open side panel
        await tryOpenSidePanel(activeTab.id, window.id);
      }
    } catch (error) {
      console.log('[TalentScreen] Error checking new window tabs:', error);
    }
  }, 1000); // Wait 1 second for page to start loading
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "openSidePanel",
    title: "Open Side Panel",
    contexts: ["all"]
  });

  chrome.contextMenus.create({
    id: "forceFillData",
    title: "Force Fill Data",
    contexts: ["all"]
  });

  console.log('[TalentScreen] Extension installed/updated - auto-open enabled for ATS sites');
});

// Handle new tabs created (e.g., opening links in new tabs)
chrome.tabs.onCreated.addListener(async (tab) => {
  // Wait a bit for the URL to be available
  setTimeout(async () => {
    try {
      const updatedTab = await chrome.tabs.get(tab.id);
      if (updatedTab.url && isATSSite(updatedTab.url)) {
        console.log('[TalentScreen] New tab created with ATS site');

        // Show badge
        chrome.action.setBadgeText({ text: '!', tabId: tab.id });
        chrome.action.setBadgeBackgroundColor({ color: '#4CAF50', tabId: tab.id });
        chrome.action.setTitle({ title: 'Click to open TalentScreen autofill', tabId: tab.id });

        // Try to open side panel
        await tryOpenSidePanel(tab.id, tab.windowId);
      }
    } catch (error) {
      // Tab might have been closed or URL not yet available
      console.log('[TalentScreen] Tab created but URL not ready yet');
    }
  }, 500);
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "openSidePanel") {
    chrome.sidePanel.open({ tabId: tab.id });
  } else if (info.menuItemId === "forceFillData") {
    chrome.storage.local.get(['resumeData', 'normalizedData', 'resumeFile'], (result) => {
      if (result.resumeData) {
        chrome.tabs.sendMessage(tab.id, {
          action: "fill_form",
          data: result.resumeData,
          normalizedData: result.normalizedData || ResumeProcessor.normalize(result.resumeData),
          resumeFile: result.resumeFile,
          manual: true
        });
      }
    });
  }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'log_fill') {
    logApplicationFill(request.data);
    sendResponse({ status: 'logged' });
  } else if (request.action === 'log_submission') {
    logApplicationSubmission(request.url);
    sendResponse({ status: 'updated' });
  } else if (request.action === 'check_sidepanel_status') {
    const windowId = sender.tab?.windowId;
    sendResponse({ isOpen: windowId ? openSidePanelWindows.has(windowId) : false });
  } else if (request.action === 'ping') {
    sendResponse({ status: 'pong' });
  } else if (request.action === 'send_feedback_email') {
    handleFeedbackEmail(request.feedback, request.emailBody);
    sendResponse({ status: 'email_queued' });
  }
  return true; // Keep message channel open for async response
});

function logApplicationFill(data) {
  chrome.storage.local.get(['pendingSubmissions'], (result) => {
    let pending = result.pendingSubmissions || {};
    try {
      if (!data.url) {
        console.warn("AutoFill: No URL provided for pending submission");
        return;
      }
      const hostname = new URL(data.url).hostname;
      pending[hostname] = { ...data, date: new Date().toISOString() };
      chrome.storage.local.set({ pendingSubmissions: pending });
    } catch (e) {
      console.error("AutoFill: Error parsing URL for pending submission:", e, data);
    }
  });
}

function logApplicationSubmission(url) {
  if (!url) {
    console.warn("AutoFill: No URL provided for submission");
    return;
  }

  try {
    const hostname = new URL(url).hostname;
    chrome.storage.local.get(['applicationHistory', 'pendingSubmissions'], (result) => {
      let history = result.applicationHistory || [];
      let pending = result.pendingSubmissions || {};

      if (pending[hostname]) {
        const data = pending[hostname];
        const oneMinuteAgo = Date.now() - 60 * 1000;
        const isDuplicate = history.some(item =>
          item.url === data.url &&
          new Date(item.date).getTime() > oneMinuteAgo
        );

        if (!isDuplicate) {
          history.push({
            ...data,
            status: 'submitted',
            date: new Date().toISOString()
          });
          if (history.length > 50) history = history.slice(-50);
          chrome.storage.local.set({ applicationHistory: history });
        }
        delete pending[hostname];
        chrome.storage.local.set({ pendingSubmissions: pending });
      }
    });
  } catch (e) {
    console.error("AutoFill: Error parsing URL for submission:", e, url);
  }
}

/**
 * Handle feedback email submission
 * Opens user's default email client with pre-filled feedback
 */
function handleFeedbackEmail(feedback, emailBody) {
  try {
    // Create mailto URL
    const recipients = 'sampath.velupula@gmail.com,recruiting@whitebox-learning.com';
    const subject = encodeURIComponent(`TalentScreen Feedback - Rating: ${feedback.rating}/5`);
    const body = encodeURIComponent(emailBody);

    // Mailto has URL length limits, so we'll open a new tab
    // The user can then send the email from their email client
    const mailtoUrl = `mailto:${recipients}?subject=${subject}&body=${body}`;

    // Try to open in new tab
    chrome.tabs.create({ url: mailtoUrl, active: false }, (tab) => {
      // Close the tab after a moment since mailto will open email client
      if (tab && tab.id) {
        setTimeout(() => {
          chrome.tabs.remove(tab.id).catch(() => {});
        }, 2000);
      }
    });

    console.log('[TalentScreen] Feedback email opened in default email client');
  } catch (error) {
    console.error('[TalentScreen] Error opening feedback email:', error);
  }
}



