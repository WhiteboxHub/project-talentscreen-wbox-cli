import React, { useState, useEffect, useRef } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';

const s = {
    // Main container
    root: { 
        display: 'flex', 
        flexDirection: 'column' as const, 
        height: '100vh', 
        width: '100vw', 
        background: '#1a1a1a', 
        color: '#e0e0e0', 
        fontFamily: '"Monaco", "Menlo", Courier, monospace', 
        overflow: 'hidden' 
    } as React.CSSProperties,
    
    // Welcome box at top
    welcomeBox: { 
        border: '1px solid #d4a574', 
        background: '#1a1a1a',
        margin: '12px',
        padding: '12px',
        borderRadius: 0,
        fontSize: 12,
        color: '#d4a574',
    } as React.CSSProperties,
    
    welcomeTitle: {
        color: '#d4a574',
        fontWeight: 'bold',
        marginBottom: 8,
        fontSize: 12,
    } as React.CSSProperties,
    
    welcomeCommand: {
        color: '#888',
        fontSize: 11,
        marginBottom: 4,
        fontStyle: 'italic' as const,
    } as React.CSSProperties,
    
    welcomePath: {
        color: '#666',
        fontSize: 11,
        marginTop: 8,
    } as React.CSSProperties,
    
    // Tips section
    tipsContainer: {
        padding: '12px',
        background: '#1a1a1a',
        color: '#e0e0e0',
        fontSize: 11,
        borderBottom: '1px solid #333',
    } as React.CSSProperties,
    
    tipTitle: {
        color: '#d4a574',
        fontWeight: 'bold',
        marginBottom: 8,
        fontSize: 11,
    } as React.CSSProperties,
    
    tipList: {
        margin: 0,
        paddingLeft: 16,
        color: '#aaa',
        lineHeight: 1.6,
        fontSize: 11,
    } as React.CSSProperties,
    
    // Terminal area
    terminalContainer: {
        flex: 1,
        display: 'flex',
        flexDirection: 'column' as const,
        overflow: 'hidden',
        background: '#0a0a0a',
        borderLeft: '4px solid #1a1a1a',
    } as React.CSSProperties,
    
    termDiv: { 
        flex: 1, 
        overflow: 'auto',
        padding: '12px',
    } as React.CSSProperties,
    
    // Input area at bottom
    inputContainer: {
        display: 'flex',
        gap: 8,
        padding: '12px',
        background: '#1a1a1a',
        borderTop: '1px solid #333',
        alignItems: 'center',
        flexShrink: 0,
    } as React.CSSProperties,
    
    inputIcon: {
        color: '#d4a574',
        fontSize: 14,
        fontWeight: 'bold',
    } as React.CSSProperties,
    
    inputField: {
        flex: 1,
        background: '#0a0a0a',
        border: '1px solid #333',
        borderRadius: 4,
        padding: '8px 12px',
        fontSize: 12,
        color: '#e0e0e0',
        outline: 'none',
        fontFamily: 'inherit',
    } as React.CSSProperties,
    
    statusIndicator: {
        width: 10,
        height: 10,
        borderRadius: '50%',
        background: '#4caf50',
        flexShrink: 0,
    } as React.CSSProperties,
};

const App = () => {
    const termRef = useRef<HTMLDivElement>(null);
    const term = useRef<XTerm | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const [connected, setConnected] = useState(false);
    const [manualUrl, setManualUrl] = useState('');
    const [lastAction, setLastAction] = useState('No recent activity');

    const sendCommand = (data: any) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(data));
        }
    };

    // ── Terminal init ──────────────────────────────────────────────────────
    useEffect(() => {
        if (!termRef.current) return;

        const t = new XTerm({
            theme: {
                background: 'transparent',
                foreground: '#e0e0e0',
                cursor: '#ff6b35',
                black: '#1a1a1a',
                red: '#ff4444',
                green: '#4caf50',
                yellow: '#ffb74d',
                blue: '#4dabf7',
                magenta: '#ba68c8',
                cyan: '#26c6da',
                white: '#e0e0e0',
                brightYellow: '#ffd54f',
                brightGreen: '#81c784',
                brightBlue: '#64b5f6',
            },
            fontFamily: '"Monaco", "Menlo", "Consolas", monospace',
            fontSize: 12,
            lineHeight: 1.5,
            allowTransparency: true,
            cursorBlink: true,
            cursorStyle: 'bar',
        });
        term.current = t;

        const fit = new FitAddon();
        t.loadAddon(fit);
        t.open(termRef.current);
        fit.fit();

        // ── Welcome panel ────────────────────────────────────────────────
        t.writeln('\x1b[33m┌─ JobCLI Agent v2.0 ──────────────────────────────────── Welcome ─┐\x1b[0m');
        t.writeln('\x1b[33m│                                                                 │\x1b[0m');
        t.writeln('\x1b[33m│  🤖 CLAUDE AGENT STRATEGIES                                      │\x1b[0m');
        t.writeln('\x1b[33m│                                                                 │\x1b[0m');
        t.writeln('\x1b[33m│  DECISION → Plan before acting. Assess if tools are needed.    │\x1b[0m');
        t.writeln('\x1b[33m│  PLAN → Break down complex tasks into clear, actionable steps. │\x1b[0m');
        t.writeln('\x1b[33m│  ACTION → Execute tools strategically. Read before writing.    │\x1b[0m');
        t.writeln('\x1b[33m│  OBSERVE → Analyze results. Update plan if needed.             │\x1b[0m');
        t.writeln('\x1b[33m│  REPEAT → Continue until task is complete or blocked.          │\x1b[0m');
        t.writeln('\x1b[33m│  FINAL → Validate results. No unintended side effects.         │\x1b[0m');
        t.writeln('\x1b[33m│                                                                 │\x1b[0m');
        t.writeln('\x1b[33m│  🛡️  SAFETY PRINCIPLES                                           │\x1b[0m');
        t.writeln('\x1b[33m│  • Never execute destructive commands without confirmation    │\x1b[0m');
        t.writeln('\x1b[33m│  • Always read files before modifying them                     │\x1b[0m');
        t.writeln('\x1b[33m│  • If uncertain → ask user instead of guessing                 │\x1b[0m');
        t.writeln('\x1b[33m│                                                                 │\x1b[0m');
        t.writeln('\x1b[33m│  🧠 CORE STRATEGIES                                              │\x1b[0m');
        t.writeln('\x1b[33m│  1. Precision over speed - Be accurate and thorough           │\x1b[0m');
        t.writeln('\x1b[33m│  2. Verification is mandatory - Always check your work         │\x1b[0m');
        t.writeln('\x1b[33m│  3. Context matters - Analyze before implementing             │\x1b[0m');
        t.writeln('\x1b[33m│  4. Tool-first approach - Use tools, not assumptions           │\x1b[0m');
        t.writeln('\x1b[33m│  5. Clear communication - Structure output for readability     │\x1b[0m');
        t.writeln('\x1b[33m│                                                                 │\x1b[0m');
        t.writeln('\x1b[33m└─────────────────────────────────────────────────────────────────┘\x1b[0m');
        t.writeln('');
        t.write('\x1b[36m> \x1b[0m');

        // ── Keyboard input ─────────────────────────────────────────────────
        let buf = '';
        t.onData((data) => {
            if (data === '\x03') {         // Ctrl+C
                t.writeln('\x1b[31m^C\x1b[0m');
                t.write('\x1b[36m> \x1b[0m');
                buf = '';
                sendCommand({ type: 'input', data: 'cancel\r' });
            } else if (data === '\r') {    // Enter
                t.writeln('');
                sendCommand({ type: 'input', data: buf + '\r' });
                buf = '';
                t.write('\x1b[36m> \x1b[0m');
            } else if (data === '\u007f') { // Backspace
                if (buf.length) { buf = buf.slice(0, -1); t.write('\b \b'); }
            } else {
                buf += data;
                t.write(data);
            }
        });

        // ── WebSocket ──────────────────────────────────────────────────────
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
        wsRef.current = ws;

        ws.onopen = () => {
            setConnected(true);
            t.writeln('\x1b[90m[ws] \x1b[32mConnected to engine.\x1b[0m');
            t.write('\x1b[36m> \x1b[0m');
        };
        ws.onclose = () => {
            setConnected(false);
            t.writeln('\r\x1b[31m[ws] Disconnected. Refresh to reconnect.\x1b[0m');
        };
        ws.onmessage = (ev) => {
            try {
                const d = JSON.parse(ev.data);
                if (d.type === 'terminal') {
                    const msg = d.message.replace(/(?<!\r)\n/g, '\r\n');
                    t.write(msg);
                } else if (d.type === 'log') {
                    t.writeln(`\r\x1b[90m[LOG] ${d.message}\x1b[0m`);
                } else if (d.type === 'phase_start') {
                    t.writeln(`\r\x1b[33m── ${(d.phase ?? 'phase').toUpperCase()} ──\x1b[0m`);
                } else if (d.type === 'error') {
                    t.writeln(`\r\x1b[31m[ERR] ${d.message}\x1b[0m`);
                }
            } catch {
                t.writeln(`\r${ev.data}`);
            }
        };

        const onResize = () => fit.fit();
        window.addEventListener('resize', onResize);

        return () => {
            window.removeEventListener('resize', onResize);
            ws.close();
            t.dispose();
        };
    }, []);

    // ── Sidebar actions ────────────────────────────────────────────────────
    const applyUrl = async () => {
        if (!manualUrl.trim()) return;
        const url = manualUrl.trim();
        setManualUrl('');
        setLastAction(`Processing: ${url}`);
        term.current?.writeln(`\r\x1b[36m[SYSTEM]\x1b[0m Processing: ${url}`);
        term.current?.write('\x1b[36m> \x1b[0m');
        try {
            await fetch('/api/apply/single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });
        } catch (e) {
            term.current?.writeln(`\r\x1b[31m[ERROR]\x1b[0m ${e}\x1b[0m`);
        }
    };

    return (
        <div style={s.root}>
            {/* Welcome Box */}
            <div style={s.welcomeBox}>
                <div style={s.welcomeTitle}>❖ Welcome to Claude Code!</div>
                <div style={s.welcomeCommand}>/help for help, /status for your current setup</div>
                <div style={s.welcomePath}>Cwd: /Users/danipower/Proyectos/ludini/mcp-code-graph</div>
            </div>

            {/* Tips Section */}
            <div style={s.tipsContainer}>
                <div style={s.tipTitle}>Tips for getting started:</div>
                <ul style={s.tipList}>
                    <li>Run /init to create a CLAUDE.md file with instructions for Claude</li>
                    <li>Run /terminal-setup to set up terminal integration</li>
                    <li>Use Claude to help with file analysis, editing, bash commands and git</li>
                    <li>Be as specific as you would with another engineer for the best results</li>
                </ul>
                <div style={{ fontSize: 11, color: '#888', marginTop: 12 }}>
                    💡 Tip: Send messages to Claude while it works to steer Claude in real-time
                </div>
            </div>

            {/* Terminal Area */}
            <div style={s.terminalContainer}>
                <div style={s.termDiv} ref={termRef} />
            </div>

            {/* Input Area */}
            <div style={s.inputContainer}>
                <span style={s.inputIcon}>💬</span>
                <input
                    style={s.inputField}
                    type="text"
                    placeholder="write a test for package.json"
                    value={manualUrl}
                    onChange={e => setManualUrl(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && applyUrl()}
                />
                <div style={{ ...s.statusIndicator, background: connected ? '#4caf50' : '#cc3333' }} />
            </div>
        </div>
    );
};

export default App;
