import type { Chat, Source } from '../types';

const now = new Date();
const hoursAgo = (h: number) => new Date(now.getTime() - h * 3600_000).toISOString();
const daysAgo = (d: number) => new Date(now.getTime() - d * 86_400_000).toISOString();

const sources: Record<string, Source> = {
  'imf-weo': {
    id: 'imf-weo',
    title: "IMF sees Pakistan's inflation rising to 9.9% in 2027 as growth slows",
    publisher: 'Business Recorder',
    section: 'World Economic Outlook, para. 3',
    date: '13 Oct 2026',
    passage:
      "The Fund's October World Economic Outlook projects Pakistan's headline inflation will rise to 9.9 percent in 2027, up from an estimated 7.1 percent this year, as base effects fade and energy prices firm. Real GDP growth is expected to ease to 3.5 percent over the same period, down from 3.6 percent in 2026, reflecting tighter fiscal policy under the ongoing programme.",
    matchStart: 46,
    matchEnd: 118,
  },
  'dawn-growth': {
    id: 'dawn-growth',
    title: "Pakistan's growth during FY27 projected at 3.5pc, inflation at 9.9pc: IMF",
    publisher: 'Dawn',
    section: 'Economic outlook',
    date: '13 Oct 2026',
    passage:
      "In its latest assessment, the IMF projected Pakistan's economy to grow 3.5 percent in FY27, slightly below this year's 3.6 percent, while inflation is seen climbing to 9.9 percent amid a weaker rupee and higher administered energy prices.",
    matchStart: 108,
    matchEnd: 160,
  },
  'boe-sept': {
    id: 'boe-sept',
    title: 'Bank rate maintained at 3.75% — September 2026 Monetary Policy Summary',
    publisher: 'Bank of England',
    section: 'Monetary Policy Committee minutes',
    date: '17 Sep 2026',
    passage:
      "The Committee voted by a majority of 7–2 to maintain Bank Rate at 3.75%. Two members preferred to reduce Bank Rate by 0.25 percentage points. Underlying services inflation has continued to ease but remains above levels consistent with the 2% target on a sustained basis.",
    matchStart: 0,
    matchEnd: 73,
  },
  'uk-sanctions': {
    id: 'uk-sanctions',
    title: 'UK sanctions three crypto exchanges tied to Russia-linked illicit finance',
    publisher: 'UK Treasury / OFSI notice',
    section: 'Designations list',
    date: '12 Oct 2026',
    passage:
      'HM Treasury designated Cryptomus, TokenSpot and Huobi Global (HTX) under the Russia sanctions regime, citing their processing of funds linked to sanctioned entities and ransomware proceeds. All UK persons are now prohibited from dealing with the designated entities.',
    matchStart: 15,
    matchEnd: 61,
  },
};

export const mockChats: Chat[] = [
  {
    id: 'chat-1',
    title: "IMF's Pakistan inflation and growth outlook",
    updatedAt: hoursAgo(1),
    messages: [
      {
        id: 'm1',
        role: 'user',
        content: "What does the IMF expect for Pakistan's inflation and GDP growth?",
        createdAt: hoursAgo(1),
      },
      {
        id: 'm2',
        role: 'assistant',
        content:
          "The IMF expects Pakistan's inflation to rise to 9.9% in 2027, up from an estimated 7.1% this year, as base effects fade and energy prices firm [1][2]. Real GDP growth is projected to ease slightly to 3.5% in 2027, down from 3.6% in 2026, reflecting tighter fiscal policy under the current programme [1].",
        citations: [
          { n: 1, sourceId: 'imf-weo' },
          { n: 2, sourceId: 'dawn-growth' },
        ],
        sources: [sources['imf-weo'], sources['dawn-growth']],
        createdAt: hoursAgo(1),
      },
    ],
  },
  {
    id: 'chat-2',
    title: 'Bank of England September rate decision',
    updatedAt: hoursAgo(20),
    messages: [
      {
        id: 'm3',
        role: 'user',
        content: 'What did the Bank of England decide on interest rates in September?',
        createdAt: hoursAgo(20),
      },
      {
        id: 'm4',
        role: 'assistant',
        content:
          'The Monetary Policy Committee voted 7–2 to hold Bank Rate at 3.75% in September, with two members preferring a 0.25 percentage point cut [1]. The Committee noted that underlying services inflation continues to ease but remains above levels consistent with the 2% target on a sustained basis [1].',
        citations: [{ n: 1, sourceId: 'boe-sept' }],
        sources: [sources['boe-sept']],
        createdAt: hoursAgo(20),
      },
    ],
  },
  {
    id: 'chat-3',
    title: 'UK sanctions on crypto exchanges',
    updatedAt: daysAgo(2),
    messages: [
      {
        id: 'm5',
        role: 'user',
        content: 'Which crypto exchanges did Britain sanction over Russia links?',
        createdAt: daysAgo(2),
      },
      {
        id: 'm6',
        role: 'assistant',
        content:
          'HM Treasury designated three exchanges — Cryptomus, TokenSpot and Huobi Global (HTX) — citing their processing of funds linked to sanctioned entities and ransomware proceeds [1]. UK persons are now prohibited from dealing with any of the designated entities [1].',
        citations: [{ n: 1, sourceId: 'uk-sanctions' }],
        sources: [sources['uk-sanctions']],
        createdAt: daysAgo(2),
      },
    ],
  },
  {
    id: 'chat-4',
    title: 'KSE-100 weekly performance recap',
    updatedAt: daysAgo(4),
    messages: [
      {
        id: 'm7',
        role: 'user',
        content: 'How did the KSE-100 perform this week?',
        createdAt: daysAgo(4),
      },
    ],
  },
  {
    id: 'chat-5',
    title: 'Solana ETF inflows this month',
    updatedAt: daysAgo(9),
    messages: [
      {
        id: 'm8',
        role: 'user',
        content: 'How have Solana ETFs performed this month?',
        createdAt: daysAgo(9),
      },
    ],
  },
  {
    id: 'chat-6',
    title: 'Japanese yen intervention risk',
    updatedAt: daysAgo(14),
    messages: [
      {
        id: 'm9',
        role: 'user',
        content: 'What is the outlook for the yen given intervention risk?',
        createdAt: daysAgo(14),
      },
    ],
  },
];

export const exampleQuestions: string[] = [
  "What does the IMF expect for Pakistan's inflation and GDP growth?",
  'How did the KSE-100 close this week?',
  'What did the Bank of England decide on interest rates in September?',
  'Which crypto exchanges did Britain sanction over Russia links?',
];

export const mockSources = sources;
