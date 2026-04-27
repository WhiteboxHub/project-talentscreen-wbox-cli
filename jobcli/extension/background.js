// Background service worker

chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error(error));
chrome.runtime.onInstalled.addListener(() => {
  console.log("Extension installed");

  chrome.contextMenus.create({
    id: "generateAIAnswer",
    title: "Generate Answer with AI",
    contexts: ["editable"]
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "generateAIAnswer") {
    chrome.tabs.sendMessage(tab.id, { action: "get_question_text" });
  }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "generate_ai_answer") {
    callOllama(request.prompt).then(result => {
      sendResponse({ text: result });
    });
    return true;
  }
});

async function callOllama(prompt) {
  const res = await fetch("http://localhost:11434/api/generate", {
    method: "POST",
    body: JSON.stringify({
      model: "llama2",
      prompt: prompt,
      stream: false
    })
  });

  const data = await res.json();
  return data.response;
}
