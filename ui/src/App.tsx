import React, { useEffect, useRef, useState } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';

const App = () => {
  const termRef = useRef<HTMLDivElement>(null);
  const term = useRef<XTerm | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const formSessionRef = useRef<null | {
    title: string;
    index: number;
    fields: any[];
  }>(null);

  // Keep state for rendering if needed, but use ref for the terminal loop
  const [formSession, setFormSessionState] = useState<null | any>(null);

  const setFormSession = (session: any) => {
    formSessionRef.current = session;
    setFormSessionState(session);
  };

  const formValuesRef = useRef<Record<string, string>>({});

  const showPrompt = () => {
    term.current?.write('\x1b[36m> \x1b[0m');
  };

  // ── FORM HANDLER ───────────────────────────────
  const processFormInput = async (input: string) => {
    const currentSession = formSessionRef.current;
    if (!currentSession) return;

    const { index, fields, title } = currentSession;
    const field = fields[index];

    formValuesRef.current[field.name] = input;

    term.current?.writeln(
      `\x1b[90m[UI] ${field.name} = ${field.type === 'password' ? '*****' : input
      }\x1b[0m`
    );

    const nextIndex = index + 1;

    if (nextIndex >= fields.length) {
      // submit
      try {
        const res = await fetch('/api/ui/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formValuesRef.current),
        });

        const text = await res.text();
        term.current?.writeln(`\x1b[32m[OK] ${text}\x1b[0m`);
      } catch (e) {
        term.current?.writeln(`\x1b[31m[ERR] ${e}\x1b[0m`);
      }

      setFormSession(null);
      formValuesRef.current = {};
      showPrompt();
      return;
    }

    // next question
    setFormSession({ title, index: nextIndex, fields });

    const next = fields[nextIndex];
    term.current?.writeln(
      `\x1b[90m${nextIndex + 1}) ${next.name}: ${next.label} (${next.type})\x1b[0m`
    );

    showPrompt();
  };

  useEffect(() => {
    if (!termRef.current) return;

    const t = new XTerm({
      theme: {
        background: '#0a0a0a',
        foreground: '#e0e0e0',
        cursor: '#ff6b35',
        selectionBackground: 'rgba(255, 107, 53, 0.3)',
        black: '#1a1a1a',
        red: '#ff5555',
        green: '#50fa7b',
        yellow: '#f1fa8c',
        blue: '#bd93f9',
        magenta: '#ff79c6',
        cyan: '#8be9fd',
        white: '#f8f8f2',
      },
      fontSize: 14,
      fontFamily: '"Fira Code", "Source Code Pro", monospace',
      cursorBlink: true,
      allowTransparency: true,
      lineHeight: 1.2,
    });

    term.current = t;

    const fit = new FitAddon();
    t.loadAddon(fit);
    t.open(termRef.current);
    fit.fit();

    // ── WELCOME ───────────────────────────────
    const printWelcome = () => {
      t.write('\x1b[H\x1b[2J'); // Move to top-left and clear viewport
      t.writeln('\x1b[1;33m❖ Welcome to JobCLI!\x1b[0m');
      t.writeln('\x1b[3m/help for help, log for application logs, /status for setup\x1b[0m');
      t.writeln(`\x1b[90mServer: ${window.location.host}\x1b[0m`);
      t.writeln('');
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        t.writeln('\x1b[90m[ws] \x1b[32mConnected to engine.\x1b[0m');
      }
    };

    printWelcome();

    // ── INPUT SYSTEM (READLINE) ─────────────
    let buffer = '';
    let cursorIndex = 0;
    let history: string[] = [];
    let historyIndex = -1;

    const redrawInput = () => {
      // Clear current line, reprint prompt and buffer, move cursor to correct position
      t.write('\x1b[2K\r\x1b[36m> \x1b[0m' + buffer);
      if (cursorIndex < buffer.length) {
        t.write(`\x1b[${buffer.length - cursorIndex}D`);
      }
    };

    t.onData((data) => {
      // Enter
      if (data === '\r') {
        t.writeln('');
        const input = buffer.trim();

        if (input) {
          history.push(input);
        }

        historyIndex = -1;
        buffer = '';
        cursorIndex = 0;

        // "clear" and "cls" handled locally
        if (input.toLowerCase() === 'clear' || input.toLowerCase() === 'cls') {
          t.clear();
          printWelcome();
          showPrompt();
          return;
        }

        const isFormActive = !!formSessionRef.current;

        if (isFormActive) {
          processFormInput(input);
        } else {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(
              JSON.stringify({ type: 'input', data: input + '\r' })
            );
          } else {
            t.writeln('\r\n\x1b[31m[ws] Error: Not connected to engine\x1b[0m');
          }
          showPrompt();
        }
      }
      // Backspace
      else if (data === '\u007f' || data === '\b') {
        if (cursorIndex > 0) {
          buffer = buffer.slice(0, cursorIndex - 1) + buffer.slice(cursorIndex);
          cursorIndex--;
          redrawInput();
        }
      }
      // Ctrl+C
      else if (data === '\x03') {
        t.writeln('^C');
        buffer = '';
        cursorIndex = 0;
        historyIndex = -1;
        if (formSessionRef.current) {
          processFormInput('/cancel');
        } else {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'input', data: 'cancel\r' }));
          }
        }
      }
      // Ctrl+L (Clear)
      else if (data === '\x0c') {
        t.clear();
        printWelcome();
        redrawInput();
      }
      // Ctrl+A (Home)
      else if (data === '\x01') {
        cursorIndex = 0;
        redrawInput();
      }
      // Ctrl+E (End)
      else if (data === '\x05') {
        cursorIndex = buffer.length;
        redrawInput();
      }
      // Ctrl+U (Clear line before cursor)
      else if (data === '\x15') {
        buffer = buffer.slice(cursorIndex);
        cursorIndex = 0;
        redrawInput();
      }
      // Ctrl+K (Clear to end of line)
      else if (data === '\x0b') {
        buffer = buffer.slice(0, cursorIndex);
        redrawInput();
      }
      // Ctrl+W (Delete previous word)
      else if (data === '\x17') {
        if (cursorIndex > 0) {
          const before = buffer.slice(0, cursorIndex);
          const after = buffer.slice(cursorIndex);
          const match = before.match(/\S+\s*$/);
          const deleteCount = match ? match[0].length : 1;
          buffer = before.slice(0, -deleteCount) + after;
          cursorIndex -= deleteCount;
          redrawInput();
        }
      }
      // Navigation: Up/Down/Left/Right
      else if (data.startsWith('\x1b[')) {
        if (data === '\x1b[A') { // Up
          if (history.length > 0) {
            if (historyIndex === -1) historyIndex = history.length - 1;
            else if (historyIndex > 0) historyIndex--;

            buffer = history[historyIndex];
            cursorIndex = buffer.length;
            redrawInput();
          }
        } else if (data === '\x1b[B') { // Down
          if (historyIndex !== -1) {
            if (historyIndex < history.length - 1) {
              historyIndex++;
              buffer = history[historyIndex];
            } else {
              historyIndex = -1;
              buffer = '';
            }
            cursorIndex = buffer.length;
            redrawInput();
          }
        } else if (data === '\x1b[D') { // Left
          if (cursorIndex > 0) {
            cursorIndex--;
            t.write('\x1b[D');
          }
        } else if (data === '\x1b[C') { // Right
          if (cursorIndex < buffer.length) {
            cursorIndex++;
            t.write('\x1b[C');
          }
        }
      }
      // Alt+Left / Alt+Right (Jump word)
      else if (data === '\x1bb' || data === '\x1b[1;3D' || data === '\x1b[1;5D') { // Alt+Left
        if (cursorIndex > 0) {
          const before = buffer.slice(0, cursorIndex);
          const match = before.match(/\S+\s*$/);
          const jump = match ? match[0].length : 1;
          cursorIndex -= jump;
          redrawInput();
        }
      }
      else if (data === '\x1bf' || data === '\x1b[1;3C' || data === '\x1b[1;5C') { // Alt+Right
        if (cursorIndex < buffer.length) {
          const after = buffer.slice(cursorIndex);
          const match = after.match(/^\s*\S+/);
          const jump = match ? match[0].length : 1;
          cursorIndex += jump;
          redrawInput();
        }
      }
      // Ignore other control sequences
      else if (data < '\x20') {
        return;
      }
      // Printable characters
      else {
        buffer = buffer.slice(0, cursorIndex) + data + buffer.slice(cursorIndex);
        cursorIndex += data.length;
        redrawInput();
      }
    });

    // ── WEBSOCKET ────────────────────────────
    // Bypass Vite proxy to avoid WS disconnection bugs
    const ws = new WebSocket(`ws://127.0.0.1:8000/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      t.writeln('\r\n\x1b[90m[ws] \x1b[32mConnected to engine.\x1b[0m');
      showPrompt();
    };

    ws.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data);

        if (d.type === 'terminal') {
          t.write(d.message.replace(/\n/g, '\r\n'));
        } else if (d.type === 'log') {
          t.writeln(`\r\n\x1b[90m[LOG] ${d.message}\x1b[0m`);
        } else if (d.type === 'error') {
          t.writeln(`\r\n\x1b[31m[ERR] ${d.message}\x1b[0m`);
        } else if (d.type === 'ui_form') {
          const { title, fields } = d;

          formValuesRef.current = {};
          setFormSession({ title, index: 0, fields });

          t.writeln(`\r\n\x1b[33m[UI FORM] ${title}\x1b[0m`);
          t.writeln(
            '\x1b[90mAnswer step-by-step. Commands: /cancel\x1b[0m'
          );

          const f = fields[0];
          t.writeln(
            `\x1b[90m1) ${f.name}: ${f.label} (${f.type})\x1b[0m`
          );

          showPrompt();
        }
      } catch {
        t.writeln('\r\n' + ev.data);
      }
    };

    ws.onclose = () => {
      t.writeln('\r\n\x1b[31m[ws] Disconnected\x1b[0m');
    };

    return () => {
      ws.close();
      t.dispose();
    };
  }, []); // Run only once

  return (
    <div style={{ height: '100vh', width: '100vw', background: '#0a0a0a' }}>
      <div ref={termRef} style={{ height: '100%', padding: '12px' }} />
    </div>
  );
};

export default App;