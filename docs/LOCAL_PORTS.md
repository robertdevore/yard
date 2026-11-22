# Local development ports

These assignments cover the repository-backed services in the Yard inventory. Each port has one owner in that inventory. Existing environment variables, CLI arguments, and saved configuration can override the project defaults. Update the corresponding Yard entry if you override a port.

| Project | Local listeners |
| --- | --- |
| Kujo Email | 8082 development HTTP API, 8942 MCP |
| CMS Contact Form | 4312 |
| Intake | 8788 dashboard, 8766 webhook listener |
| Kujo VideoOps | 8789 HTTP API |
| Kujo Source | 8790 HTTP API, 8797 optional artifact bootstrap |
| BZBY | 4302 API, 4303 web |
| Agent Black Box | 4180 |
| Kujo Replay Lab | 4181 Canvas |
| Kujo Foreman | 8791 Strands bridge, 4182 web |
| Workcell Studio | 4183 |
| Kujo Ability Gateway | 8792 |
| Kujo Ability DevKit | 8793 |
| Kujo OpenAI | 8794 optional remote origin |
| Kujo Payments | 8795 executor gateway, 8796 sandbox merchant |
| Kujo CRUD API | 4100 API, 3002 playground |
| Laravel CMS | 8000 API, 3003 frontend, 5175 Vite assets |

RepoRadar retains 8080, Cron Control Surface 8765, Kujo RAG 8787, AI Chat 4173 for a standalone run, CMS Experience 4300 and 4301, Website Cloner 4310 and 4311, Hey Meadow 3000 and 8081, and Kujo Docs MCP 8941. An existing installation can have a separate assignment, such as AI Chat running on 4174 under a LaunchAgent.

Ports inside containers and protocol-specific deployment settings have separate scopes. Registering an endpoint for observation in Yard keeps service ownership with the tool that launched it.
