import type { DemoRoute } from './types'

export const claudeCodeRoutes: DemoRoute[] = [
  // List sessions
  {
    method: 'GET',
    pattern: /^\/admin\/claude-code\/sessions$/,
    handler: () => ({
      sessions: [
        {
          id: 'cc-demo001',
          cli_session_id: 'demo-cli-session-1',
          title: 'Fix login bug',
          owner_id: 1,
          status: 'completed',
          model: 'claude-opus-4-6',
          total_turns: 3,
          max_turns: 50,
          working_directory: '/opt/ai-secretary',
          created: new Date(Date.now() - 3600000).toISOString(),
          updated: new Date(Date.now() - 3000000).toISOString(),
        },
        {
          id: 'cc-demo002',
          cli_session_id: 'demo-cli-session-2',
          title: 'Add new endpoint',
          owner_id: 1,
          status: 'completed',
          model: 'claude-opus-4-6',
          total_turns: 5,
          max_turns: 50,
          working_directory: '/opt/ai-secretary',
          created: new Date(Date.now() - 7200000).toISOString(),
          updated: new Date(Date.now() - 6000000).toISOString(),
        },
      ],
    }),
  },
  // Get session
  {
    method: 'GET',
    pattern: /^\/admin\/claude-code\/sessions\/([^/]+)$/,
    handler: ({ matches }) => ({
      session: {
        id: matches[1],
        cli_session_id: 'demo-cli-session-1',
        title: 'Demo session',
        owner_id: 1,
        status: 'completed',
        model: 'claude-opus-4-6',
        total_turns: 3,
        max_turns: 50,
        working_directory: '/opt/ai-secretary',
        created: new Date().toISOString(),
        updated: new Date().toISOString(),
      },
    }),
  },
  // Delete session
  {
    method: 'DELETE',
    pattern: /^\/admin\/claude-code\/sessions\/([^/]+)$/,
    handler: () => ({ status: 'deleted' }),
  },
]
