import { useEffect, useState } from 'react';
import { Sidebar } from './components/Sidebar/Sidebar';
import { ChatPanel } from './components/Chat/ChatPanel';
import { CitationPanel } from './components/CitationPanel/CitationPanel';
import { SettingsModal } from './components/Settings/SettingsModal';
import { mockChats } from './data/mockData';
import { streamAnswer } from './services/api';
import type { Chat, ChatMessage, Source, ThemeMode } from './types';
import './styles/global.css';

function newChatId() {
  return `chat-${Date.now()}`;
}

function newMessageId() {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export default function App() {
  const [chats, setChats] = useState<Chat[]>(mockChats);
  const [activeId, setActiveId] = useState<string | null>(mockChats[0]?.id ?? null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.innerWidth <= 760);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [citationSource, setCitationSource] = useState<Source | null>(null);
  const [theme, setTheme] = useState<ThemeMode>('light');
  const [isSearching, setIsSearching] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const activeChat = chats.find((c) => c.id === activeId) ?? null;

  function updateChat(id: string, updater: (chat: Chat) => Chat) {
    setChats((prev) => prev.map((c) => (c.id === id ? updater(c) : c)));
  }

  function handleNewChat() {
    const chat: Chat = { id: newChatId(), title: 'New chat', updatedAt: new Date().toISOString(), messages: [] };
    setChats((prev) => [chat, ...prev]);
    setActiveId(chat.id);
  }

  function handleDeleteChat(id: string) {
    setChats((prev) => prev.filter((c) => c.id !== id));
    if (activeId === id) setActiveId(null);
  }

  function handleRenameChat(id: string, title: string) {
    updateChat(id, (c) => ({ ...c, title }));
  }

  function handleClearChat() {
    if (!activeId) return;
    updateChat(activeId, (c) => ({ ...c, messages: [] }));
  }

  async function handleSend(text: string) {
    let chatId = activeId;

    if (!chatId) {
      const chat: Chat = { id: newChatId(), title: text.slice(0, 48), updatedAt: new Date().toISOString(), messages: [] };
      setChats((prev) => [chat, ...prev]);
      chatId = chat.id;
      setActiveId(chatId);
    }

    const userMessage: ChatMessage = {
      id: newMessageId(),
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
    };

    updateChat(chatId, (c) => ({
      ...c,
      title: c.messages.length === 0 ? text.slice(0, 48) : c.title,
      updatedAt: new Date().toISOString(),
      messages: [...c.messages, userMessage],
    }));

    setIsSearching(true);

    const assistantId = newMessageId();
    let assistantAdded = false;

    for await (const event of streamAnswer(text)) {
      if (event.type === 'retrieval') {
        setIsSearching(false);
        setIsStreaming(true);
        const assistantMessage: ChatMessage = {
          id: assistantId,
          role: 'assistant',
          content: '',
          sources: event.sources,
          createdAt: new Date().toISOString(),
        };
        updateChat(chatId, (c) => ({ ...c, messages: [...c.messages, assistantMessage] }));
        assistantAdded = true;
      } else if (event.type === 'token') {
        updateChat(chatId, (c) => ({
          ...c,
          messages: c.messages.map((m) => (m.id === assistantId ? { ...m, content: m.content + event.text } : m)),
        }));
      } else if (event.type === 'done') {
        updateChat(chatId, (c) => ({
          ...c,
          messages: c.messages.map((m) => (m.id === assistantId ? { ...m, citations: event.citations } : m)),
        }));
        setIsStreaming(false);
      } else if (event.type === 'busy' || event.type === 'error') {
        setIsSearching(false);
        setIsStreaming(false);
        if (!assistantAdded) {
          updateChat(chatId, (c) => ({
            ...c,
            messages: [
              ...c.messages,
              { id: assistantId, role: 'assistant', content: event.message, createdAt: new Date().toISOString() },
            ],
          }));
        }
      }
    }
  }

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <Sidebar
        chats={chats}
        activeId={activeId}
        collapsed={sidebarCollapsed}
        onSelect={setActiveId}
        onNewChat={handleNewChat}
        onRename={handleRenameChat}
        onDelete={handleDeleteChat}
        onOpenSettings={() => setSettingsOpen(true)}
        onCollapse={() => setSidebarCollapsed(true)}
      />
      <ChatPanel
        chat={activeChat}
        onToggleSidebar={() => setSidebarCollapsed((v) => !v)}
        onSend={handleSend}
        onCiteClick={setCitationSource}
        onClearChat={handleClearChat}
        isSearching={isSearching}
        isStreaming={isStreaming}
      />
      <CitationPanel source={citationSource} onClose={() => setCitationSource(null)} />
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} theme={theme} onThemeChange={setTheme} />
    </div>
  );
}
