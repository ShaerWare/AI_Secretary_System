/**
 * AI Secretary Chat Widget
 * Replaces Replain with your own AI assistant (Марина/Анна)
 *
 * Usage:
 * <script>
 *   window.aiChatSettings = {
 *     apiUrl: 'https://your-ngrok-url.ngrok.io',
 *     title: 'AI Ассистент',
 *     greeting: 'Здравствуйте! Чем могу помочь?',
 *     placeholder: 'Введите сообщение...',
 *     primaryColor: '#c2410c'
 *   };
 * </script>
 * <script src="ai-chat-widget.js"></script>
 */

(async function() {
  'use strict';

  const defaultSettings = {
    apiUrl: '',
    title: 'AI Ассистент',
    greeting: 'Здравствуйте! Компания Шаервэй Ди-Иджитал, чем могу помочь?',
    placeholder: 'Введите сообщение...',
    primaryColor: '#c2410c',
    placeholderColor: '',
    placeholderFont: '',
    buttonIcon: 'chat', // chat, headset, robot, comment, support, wave
    position: 'right', // 'left' or 'right'
    sessionKey: 'ai_chat_session'
  };

  const BUTTON_ICONS = {
    chat: '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z"/></svg>',
    headset: '<svg viewBox="0 0 24 24"><path d="M12 1a9 9 0 0 0-9 9v7c0 1.66 1.34 3 3 3h3v-8H5v-2c0-3.87 3.13-7 7-7s7 3.13 7 7v2h-4v8h3c1.66 0 3-1.34 3-3v-7a9 9 0 0 0-9-9z"/></svg>',
    robot: '<svg viewBox="0 0 24 24"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2zM7.5 13A2.5 2.5 0 0 0 5 15.5 2.5 2.5 0 0 0 7.5 18a2.5 2.5 0 0 0 2.5-2.5A2.5 2.5 0 0 0 7.5 13zm9 0a2.5 2.5 0 0 0-2.5 2.5 2.5 2.5 0 0 0 2.5 2.5 2.5 2.5 0 0 0 2.5-2.5 2.5 2.5 0 0 0-2.5-2.5z"/></svg>',
    comment: '<svg viewBox="0 0 24 24"><path d="M12 3C6.5 3 2 6.6 2 11c0 2.5 1.4 4.7 3.5 6.2-.3 1.6-1.2 3-2.4 4 2.2-.1 4.4-1 6-2.5.9.2 1.9.3 2.9.3 5.5 0 10-3.6 10-8s-4.5-8-10-8z"/></svg>',
    support: '<svg viewBox="0 0 24 24"><path d="M11.5 2C6.8 2 3 5.8 3 10.5c0 1.6.4 3.1 1.2 4.4L2 21l6.1-2.2c1.3.8 2.8 1.2 4.4 1.2h.5c4.2-.3 7.5-3.8 7.5-8 0-4.7-3.8-8.5-8.5-8.5h-.5zm5 11h-9c-.3 0-.5-.2-.5-.5s.2-.5.5-.5h9c.3 0 .5.2.5.5s-.2.5-.5.5zm0-3h-9c-.3 0-.5-.2-.5-.5s.2-.5.5-.5h9c.3 0 .5.2.5.5s-.2.5-.5.5z"/></svg>',
    wave: '<svg viewBox="0 0 24 24"><path d="M7.03 4.95c-.29-.29-.77-.29-1.06 0L4.89 6.03c-2.34 2.34-2.34 6.14 0 8.49l4.59 4.59c2.34 2.34 6.14 2.34 8.49 0l1.08-1.08c.29-.29.29-.77 0-1.06L7.03 4.95zm14.46 6.02c.39-.39.39-1.02 0-1.41L18.95 7.01c-.39-.39-1.02-.39-1.41 0-.39.39-.39 1.02 0 1.41l1.06 1.06-4.23 4.23 1.06 1.06 4.23-4.23 1.06 1.06c.39.39 1.02.39 1.41 0l.36-.37zM8.44 17.8c-.39.39-.39 1.02 0 1.41.39.39 1.02.39 1.41 0l4.23-4.23-1.06-1.06-4.58 3.88z"/></svg>'
  };

  const settings = { ...defaultSettings, ...(window.aiChatSettings || {}) };

  // Per-instance session key to avoid collisions between multiple widgets
  if (settings.instanceId) {
    settings.sessionKey = `ai_chat_session_${settings.instanceId}`;
  }

  if (!settings.apiUrl) {
    console.error('AI Chat Widget: apiUrl is required in window.aiChatSettings');
    return;
  }

  // Runtime check: is widget enabled on the server?
  try {
    const instanceParam = settings.instanceId || 'default';
    const statusRes = await fetch(`${settings.apiUrl}/widget/status?instance=${instanceParam}`);
    if (statusRes.ok) {
      const statusData = await statusRes.json();
      if (!statusData.enabled) {
        return; // Widget is disabled — don't render
      }
    }
  } catch (e) {
    // If check fails (network error, CORS, etc.) — render anyway (fail-open)
  }

  // State
  let isOpen = false;
  let sessionId = getCookie(settings.sessionKey) || localStorage.getItem(settings.sessionKey);
  let messages = [];
  let isStreaming = false;

  // Create styles
  const styles = document.createElement('style');
  styles.textContent = `
    .ai-chat-widget {
      --ai-primary: ${settings.primaryColor};
      --ai-primary-hover: ${adjustColor(settings.primaryColor, -15)};
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      z-index: 999999;
    }

    .ai-chat-button {
      position: fixed !important;
      bottom: 20px !important;
      ${settings.position}: 20px !important;
      width: 60px !important;
      height: 60px !important;
      border-radius: 50% !important;
      background: var(--ai-primary) !important;
      border: none !important;
      cursor: pointer !important;
      box-shadow: 0 4px 20px rgba(0,0,0,0.25) !important;
      transition: transform 0.2s, background 0.2s;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      z-index: 999999 !important;
      opacity: 1 !important;
      visibility: visible !important;
      pointer-events: auto !important;
    }

    .ai-chat-button:hover {
      transform: scale(1.05);
      background: var(--ai-primary-hover);
    }

    .ai-chat-button svg {
      width: 28px;
      height: 28px;
      fill: white;
    }

    .ai-chat-button.has-unread::after {
      content: '';
      position: absolute;
      top: 0;
      right: 0;
      width: 16px;
      height: 16px;
      background: #ef4444;
      border-radius: 50%;
      border: 3px solid white;
    }

    .ai-chat-window {
      position: fixed;
      bottom: 90px;
      ${settings.position}: 20px;
      width: 380px;
      max-width: calc(100vw - 40px);
      height: 520px;
      max-height: calc(100vh - 120px);
      background: white;
      border-radius: 16px;
      box-shadow: 0 10px 40px rgba(0,0,0,0.2);
      display: none;
      flex-direction: column;
      overflow: hidden;
      z-index: 999999;
    }

    .ai-chat-window.open {
      display: flex;
      animation: ai-slide-up 0.3s ease-out;
    }

    @keyframes ai-slide-up {
      from {
        opacity: 0;
        transform: translateY(20px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .ai-chat-header {
      background: var(--ai-primary);
      color: white;
      padding: 16px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .ai-chat-header-title {
      font-weight: 600;
      font-size: 16px;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .ai-chat-header-title::before {
      content: '';
      width: 10px;
      height: 10px;
      background: #22c55e;
      border-radius: 50%;
    }

    .ai-chat-close {
      background: none;
      border: none;
      color: white;
      cursor: pointer;
      padding: 4px;
      opacity: 0.8;
      transition: opacity 0.2s;
    }

    .ai-chat-close:hover {
      opacity: 1;
    }

    .ai-chat-close svg {
      width: 20px;
      height: 20px;
    }

    .ai-chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: #f9fafb;
    }

    .ai-chat-message {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 12px;
      word-wrap: break-word;
      white-space: pre-wrap;
    }

    .ai-chat-message.user {
      align-self: flex-end;
      background: var(--ai-primary);
      color: white;
      border-bottom-right-radius: 4px;
    }

    .ai-chat-message.assistant {
      align-self: flex-start;
      background: white;
      color: #1f2937;
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }

    .ai-chat-message.typing {
      display: flex;
      gap: 4px;
      padding: 14px 18px;
    }

    .ai-chat-message.typing span {
      width: 8px;
      height: 8px;
      background: #9ca3af;
      border-radius: 50%;
      animation: ai-typing 1s infinite;
    }

    .ai-chat-message.typing span:nth-child(2) {
      animation-delay: 0.2s;
    }

    .ai-chat-message.typing span:nth-child(3) {
      animation-delay: 0.4s;
    }

    @keyframes ai-typing {
      0%, 100% { opacity: 0.4; transform: scale(1); }
      50% { opacity: 1; transform: scale(1.1); }
    }

    .ai-chat-input-area {
      padding: 12px 16px;
      background: white;
      border-top: 1px solid #e5e7eb;
      display: flex;
      gap: 10px;
    }

    .ai-chat-input {
      flex: 1;
      padding: 10px 14px;
      border: 1px solid #e5e7eb;
      border-radius: 24px;
      outline: none;
      font-size: 14px;
      color: #1f2937;
      resize: none;
      max-height: 100px;
      font-family: inherit;
    }

    .ai-chat-input::placeholder {
      color: ${settings.placeholderColor || '#9ca3af'};
      ${settings.placeholderFont ? `font-family: '${settings.placeholderFont}', sans-serif;` : ''}
    }

    .ai-chat-input:focus {
      border-color: var(--ai-primary);
    }

    .ai-chat-send {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: var(--ai-primary);
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s, transform 0.1s;
    }

    .ai-chat-send:hover:not(:disabled) {
      background: var(--ai-primary-hover);
    }

    .ai-chat-send:active:not(:disabled) {
      transform: scale(0.95);
    }

    .ai-chat-send:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .ai-chat-send svg {
      width: 18px;
      height: 18px;
      fill: white;
    }

    .ai-chat-error {
      background: #fef2f2;
      color: #dc2626;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 13px;
      text-align: center;
    }

    .ai-chat-powered {
      text-align: center;
      padding: 8px;
      font-size: 11px;
      color: #9ca3af;
      background: white;
    }

    .ai-chat-powered a {
      color: var(--ai-primary);
      text-decoration: none;
    }

    @media (max-width: 480px) {
      .ai-chat-window {
        bottom: 0;
        ${settings.position}: 0;
        width: 100%;
        max-width: 100%;
        height: 100%;
        max-height: 100%;
        border-radius: 0;
      }

      .ai-chat-button {
        bottom: 15px;
        ${settings.position}: 15px;
      }
    }
  `;
  document.head.appendChild(styles);

  // Create widget HTML
  const widget = document.createElement('div');
  widget.className = 'ai-chat-widget';
  widget.innerHTML = `
    <button class="ai-chat-button" aria-label="Open chat">
      ${BUTTON_ICONS[settings.buttonIcon] || BUTTON_ICONS.chat}
    </button>
    <div class="ai-chat-window">
      <div class="ai-chat-header">
        <span class="ai-chat-header-title">${escapeHtml(settings.title)}</span>
        <button class="ai-chat-close" aria-label="Close chat">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>
      <div class="ai-chat-messages" id="ai-chat-messages"></div>
      <div class="ai-chat-input-area">
        <textarea class="ai-chat-input" placeholder="${escapeHtml(settings.placeholder)}" rows="1"></textarea>
        <button class="ai-chat-send" aria-label="Send message">
          <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
        </button>
      </div>
      <div class="ai-chat-powered">
        Powered by <a href="https://shaerware.digital" target="_blank">ShaerWare AI</a>
      </div>
    </div>
  `;
  document.body.appendChild(widget);

  // Elements
  const button = widget.querySelector('.ai-chat-button');
  const window_ = widget.querySelector('.ai-chat-window');
  const closeBtn = widget.querySelector('.ai-chat-close');
  const messagesEl = widget.querySelector('#ai-chat-messages');
  const input = widget.querySelector('.ai-chat-input');
  const sendBtn = widget.querySelector('.ai-chat-send');

  // Event handlers
  button.addEventListener('click', toggleChat);
  closeBtn.addEventListener('click', toggleChat);
  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize input
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
  });

  let historyLoaded = false;
  // Cache for preloaded history (fetched on page load, rendered on open)
  let pendingHistory = null;

  async function preloadHistory() {
    if (historyLoaded || !sessionId) return;
    historyLoaded = true;

    try {
      const res = await fetch(`${settings.apiUrl}/widget/chat/session/${sessionId}`);
      if (res.ok) {
        const data = await res.json();
        const history = data.session && data.session.messages;
        if (history && history.length > 0) {
          pendingHistory = history;
          return;
        }
      } else if (res.status === 404) {
        // Stale session — clear and start fresh
        sessionId = null;
        deleteCookie(settings.sessionKey);
        localStorage.removeItem(settings.sessionKey);
        sessionStorage.removeItem(settings.sessionKey + '_open');
      }
    } catch (e) {
      // Network error — allow retry on next open
      historyLoaded = false;
    }
  }

  function renderHistory() {
    if (messages.length > 0) return; // Already rendered
    addMessage('assistant', settings.greeting);
    if (pendingHistory) {
      for (const msg of pendingHistory) {
        if (msg.role === 'user' || msg.role === 'assistant') {
          addMessage(msg.role, msg.content);
        }
      }
      pendingHistory = null;
    }
  }

  function toggleChat() {
    isOpen = !isOpen;
    window_.classList.toggle('open', isOpen);
    button.classList.remove('has-unread');
    // Remember open/closed state across page navigations
    if (isOpen) {
      sessionStorage.setItem(settings.sessionKey + '_open', '1');
    } else {
      sessionStorage.removeItem(settings.sessionKey + '_open');
    }

    if (isOpen && messages.length === 0) {
      renderHistory();
    }
  }

  // Preload history immediately on page load
  const historyReady = preloadHistory();

  // Auto-open if chat was open before page navigation
  if (sessionStorage.getItem(settings.sessionKey + '_open') === '1') {
    historyReady.then(() => {
      isOpen = true;
      window_.classList.toggle('open', true);
      renderHistory();
    });
  }

  function addMessage(role, content, isTemp = false) {
    if (!isTemp) {
      messages.push({ role, content });
    }

    const messageEl = document.createElement('div');
    messageEl.className = `ai-chat-message ${role}`;

    if (content === '...') {
      messageEl.classList.add('typing');
      messageEl.innerHTML = '<span></span><span></span><span></span>';
    } else {
      messageEl.textContent = content;
    }

    if (isTemp) {
      messageEl.id = 'ai-chat-typing';
    }

    messagesEl.appendChild(messageEl);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    return messageEl;
  }

  function removeTyping() {
    const typing = document.getElementById('ai-chat-typing');
    if (typing) typing.remove();
  }

  async function sendMessage() {
    const content = input.value.trim();
    if (!content || isStreaming) return;

    input.value = '';
    input.style.height = 'auto';
    addMessage('user', content);

    isStreaming = true;
    sendBtn.disabled = true;
    addMessage('assistant', '...', true);

    try {
      // Build headers with auth token if available
      const hdrs = { 'Content-Type': 'application/json' };
      const jwt = localStorage.getItem('admin_token');
      if (jwt) hdrs['Authorization'] = 'Bearer ' + jwt;

      // Create session if needed
      if (!sessionId) {
        const body = {};
        if (settings.instanceId) {
          body.source = 'widget';
          body.source_id = settings.instanceId;
        }
        // Use public widget endpoint if no JWT, else use admin endpoint
        const createUrl = jwt
          ? `${settings.apiUrl}/admin/chat/sessions`
          : `${settings.apiUrl}/widget/chat/session`;
        const sessionRes = await fetch(createUrl, {
          method: 'POST',
          headers: hdrs,
          body: JSON.stringify(body)
        });
        const sessionData = await sessionRes.json();
        sessionId = sessionData.session.id;
        setCookie(settings.sessionKey, sessionId, SESSION_TTL_DAYS);
        localStorage.setItem(settings.sessionKey, sessionId);
      }

      // Stream response
      const streamBody = { content };
      if (settings.instanceId) {
        streamBody.widget_instance_id = settings.instanceId;
      }
      // Use public widget endpoint if no JWT
      const streamUrl = jwt
        ? `${settings.apiUrl}/admin/chat/sessions/${sessionId}/stream`
        : `${settings.apiUrl}/widget/chat/session/${sessionId}/stream`;
      const response = await fetch(streamUrl, {
        method: 'POST',
        headers: hdrs,
        body: JSON.stringify(streamBody)
      });

      if (!response.ok) {
        if (response.status === 429) {
          throw new Error('RATE_LIMIT');
        }
        throw new Error(`HTTP ${response.status}`);
      }

      removeTyping();

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantContent = '';
      let messageEl = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === 'chunk' && data.content) {
                assistantContent += data.content;

                if (!messageEl) {
                  messageEl = addMessage('assistant', assistantContent);
                  messages.pop(); // Remove empty message added by addMessage
                } else {
                  messageEl.textContent = assistantContent;
                }
                messagesEl.scrollTop = messagesEl.scrollHeight;
              } else if (data.type === 'done' || data.type === 'assistant_message') {
                if (assistantContent) {
                  messages.push({ role: 'assistant', content: assistantContent });
                }
              } else if (data.type === 'error') {
                throw new Error(data.content || 'Stream error');
              }
            } catch (e) {
              // Ignore parse errors for incomplete chunks
            }
          }
        }
      }

    } catch (error) {
      console.error('AI Chat error:', error);
      removeTyping();

      const errorEl = document.createElement('div');
      errorEl.className = 'ai-chat-error';
      if (error.message === 'RATE_LIMIT') {
        errorEl.textContent = 'Превышен лимит сообщений. Пожалуйста, попробуйте позже.';
      } else {
        errorEl.textContent = 'Не удалось отправить сообщение. Попробуйте позже.';
      }
      messagesEl.appendChild(errorEl);

      // Remove error after 5s
      setTimeout(() => errorEl.remove(), 5000);

      // Clear invalid session on auth/not-found errors
      if (error.message.includes('404') || error.message.includes('401') || error.message.includes('Session')) {
        sessionId = null;
        deleteCookie(settings.sessionKey);
        localStorage.removeItem(settings.sessionKey);
      }
    } finally {
      isStreaming = false;
      sendBtn.disabled = false;
    }
  }

  // Helpers
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function adjustColor(color, percent) {
    const num = parseInt(color.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = Math.max(0, Math.min(255, (num >> 16) + amt));
    const G = Math.max(0, Math.min(255, ((num >> 8) & 0x00FF) + amt));
    const B = Math.max(0, Math.min(255, (num & 0x0000FF) + amt));
    return '#' + (0x1000000 + R * 0x10000 + G * 0x100 + B).toString(16).slice(1);
  }

  // Cookie helpers for cross-origin session persistence
  const SESSION_TTL_DAYS = 30;

  function setCookie(name, value, days) {
    const expires = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie = name + '=' + encodeURIComponent(value) + ';expires=' + expires + ';path=/;SameSite=None;Secure';
  }

  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
  }

  function deleteCookie(name) {
    document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;SameSite=None;Secure';
  }

  // Expose API
  window.aiChat = {
    open: () => { if (!isOpen) toggleChat(); },
    close: () => { if (isOpen) toggleChat(); },
    clearSession: () => {
      sessionId = null;
      messages = [];
      historyLoaded = false;
      pendingHistory = null;
      deleteCookie(settings.sessionKey);
      localStorage.removeItem(settings.sessionKey);
      sessionStorage.removeItem(settings.sessionKey + '_open');
      messagesEl.innerHTML = '';
    }
  };

})();
