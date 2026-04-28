/**
 * chrome-mock.js
 * Full Chrome Extension API mock for Jest (jsdom environment).
 * Covers: chrome.storage.local, chrome.runtime, chrome.tabs,
 *         chrome.contextMenus, chrome.sidePanel, chrome.windows.
 */

const chromeMock = {
  storage: {
    local: {
      _store: {},
      get(keys, callback) {
        const result = {};
        if (typeof keys === 'string') keys = [keys];
        if (Array.isArray(keys)) {
          keys.forEach(k => { if (this._store[k] !== undefined) result[k] = this._store[k]; });
        } else if (keys === null || typeof keys === 'object') {
          Object.keys(this._store).forEach(k => { result[k] = this._store[k]; });
        }
        if (callback) callback(result);
        return Promise.resolve(result);
      },
      set(items, callback) {
        Object.assign(this._store, items);
        if (callback) callback();
        return Promise.resolve();
      },
      remove(keys, callback) {
        if (typeof keys === 'string') keys = [keys];
        keys.forEach(k => delete this._store[k]);
        if (callback) callback();
        return Promise.resolve();
      },
      clear(callback) {
        this._store = {};
        if (callback) callback();
        return Promise.resolve();
      }
    },
    onChanged: {
      addListener: jest.fn(),
      removeListener: jest.fn()
    }
  },
  runtime: {
    id: 'test-extension-id',
    lastError: null,
    sendMessage: jest.fn((msg, callback) => {
      if (callback) callback({ isOpen: false });
      return Promise.resolve();
    }),
    onMessage: {
      addListener: jest.fn(),
      removeListener: jest.fn()
    },
    onInstalled: {
      addListener: jest.fn()
    },
    connect: jest.fn(() => ({
      postMessage: jest.fn(),
      onDisconnect: { addListener: jest.fn() },
      onMessage: { addListener: jest.fn() }
    }))
  },
  tabs: {
    query: jest.fn((opts, callback) => {
      if (callback) callback([{ id: 1, windowId: 1, url: 'https://jobs.lever.co/example/test' }]);
      return Promise.resolve([]);
    }),
    sendMessage: jest.fn((tabId, msg, callback) => {
      if (callback) callback({ status: 'ok' });
      return Promise.resolve();
    }),
    create: jest.fn((opts, callback) => {
      if (callback) callback({ id: 99 });
      return Promise.resolve({ id: 99 });
    }),
    remove: jest.fn((tabId, callback) => {
      if (callback) callback();
      return Promise.resolve();
    })
  },
  contextMenus: {
    create: jest.fn(),
    onClicked: { addListener: jest.fn() }
  },
  sidePanel: {
    setPanelBehavior: jest.fn(() => Promise.resolve()),
    open: jest.fn()
  },
  windows: {
    getCurrent: jest.fn((callback) => {
      if (callback) callback({ id: 1 });
      return Promise.resolve({ id: 1 });
    })
  }
};

// Expose globally as `chrome`
global.chrome = chromeMock;

// Utility: reset storage and mocks between tests
global.resetChromeMock = () => {
  chromeMock.storage.local._store = {};
  chromeMock.runtime.lastError = null;
  jest.clearAllMocks();

  // Re-apply sendMessage default
  chromeMock.runtime.sendMessage.mockImplementation((msg, callback) => {
    if (callback) callback({ isOpen: false });
    return Promise.resolve();
  });
};
