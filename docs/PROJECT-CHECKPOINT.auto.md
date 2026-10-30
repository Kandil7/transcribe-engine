# Auto Checkpoint (pre-compaction snapshot)

- Time: 2026-10-30T13:47:10.687Z
- Session: ses_f89262437ffeyTgTBujokgXJjJ
- Project: D:\AI\Projects\transcribe-engine

## Recent user prompts (tail)
- **user**: Initialize codebase-memory-mcp + graphify for the current or specified project.

## Available MCP tools (server prefixes)

- `codebase-memory-mcp_*` — structural graph (index, search, trace, architecture)
- `graphify_*` — multimodal graph (query, god_nodes, shortest_path, PR impact)
- `repomix_*` — context packing (pack_codebase, grep output)
- `code-review-graph_*` — review blast-radius (detect_changes, get_impact_radius)

## Steps

### 1. Detect project

- If `` is provided: use it as the project path or name.
  - If it's a path (contains `/` or `\`), resolve it.
  - If it's a name, look under `D:\AI\Projects\<name>`.
- If no arguments: use the current working directory.
- Verify the path exists and contains source code.

### 2. Check index status

Call `codebase-memory-mcp_list_projects` to see if this project is already indexed.

- If indexed: call `codebase-memory-mcp_index_status` to get current stats.
- If not indexed: proceed to step 3.

### 3. Index the project (if needed)

Call `codebase-memory-mcp_index_repository` with:
- `repo_path`: the detected project root
- `project`: derived project name (lowercase, hyphens for spaces)
- `mode`: `"full"`

Report indexing progress. Wait for completion.

### 4. Get architecture data

Call `codebase-memory-mcp_get_architecture` with:
- `project`: the project name
- `aspects`: `["all"]`

This returns: languages, packages, entry points, routes, hotspots, boundaries, layers, clusters, cycles, file tree.

### 5. Generate Mermaid di
- **user**: Initialize codebase-memory-mcp + graphify for the current or specified project.

## Available MCP tools (server prefixes)

- `codebase-memory-mcp_*` — structural graph (index, search, trace, architecture)
- `graphify_*` — multimodal graph (query, god_nodes, shortest_path, PR impact)
- `repomix_*` — context packing (pack_codebase, grep output)
- `code-review-graph_*` — review blast-radius (detect_changes, get_impact_radius)

## Steps

### 1. Detect project

- If `` is provided: use it as the project path or name.
  - If it's a path (contains `/` or `\`), resolve it.
  - If it's a name, look under `D:\AI\Projects\<name>`.
- If no arguments: use the current working directory.
- Verify the path exists and contains source code.

### 2. Check index status

Call `codebase-memory-mcp_list_projects` to see if this project is already indexed.

- If indexed: call `codebase-memory-mcp_index_status` to get current stats.
- If not indexed: proceed to step 3.

### 3. Index the project (if needed)

Call `codebase-memory-mcp_index_repository` with:
- `repo_path`: the detected project root
- `project`: derived project name (lowercase, hyphens for spaces)
- `mode`: `"full"`

Report indexing progress. Wait for completion.

### 4. Get architecture data

Call `codebase-memory-mcp_get_architecture` with:
- `project`: the project name
- `aspects`: `["all"]`

This returns: languages, packages, entry points, routes, hotspots, boundaries, layers, clusters, cycles, file tree.

### 5. Generate Mermaid di
- **user**: Initialize codebase-memory-mcp + graphify for the current or specified project.

## Available MCP tools (server prefixes)

- `codebase-memory-mcp_*` — structural graph (index, search, trace, architecture)
- `graphify_*` — multimodal graph (query, god_nodes, shortest_path, PR impact)
- `repomix_*` — context packing (pack_codebase, grep output)
- `code-review-graph_*` — review blast-radius (detect_changes, get_impact_radius)

## Steps

### 1. Detect project

- If `transcribe-engine` is provided: use it as the project path or name.
  - If it's a path (contains `/` or `\`), resolve it.
  - If it's a name, look under `D:\AI\Projects\<name>`.
- If no arguments: use the current working directory.
- Verify the path exists and contains source code.

### 2. Check index status

Call `codebase-memory-mcp_list_projects` to see if this project is already indexed.

- If indexed: call `codebase-memory-mcp_index_status` to get current stats.
- If not indexed: proceed to step 3.

### 3. Index the project (if needed)

Call `codebase-memory-mcp_index_repository` with:
- `repo_path`: the detected project root
- `project`: derived project name (lowercase, hyphens for spaces)
- `mode`: `"full"`

Report indexing progress. Wait for completion.

### 4. Get architecture data

Call `codebase-memory-mcp_get_architecture` with:
- `project`: the project name
- `aspects`: `["all"]`

This returns: languages, packages, entry points, routes, hotspots, boundaries, layers, clusters, cycles, file tree.

### 5. Ge

> Regenerate a curated checkpoint with /checkpoint.