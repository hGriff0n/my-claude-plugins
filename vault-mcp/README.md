Contextualizing spec for vault mcp server. This server basically tries to expose vault details like tasks, efforts, etc in an api so dashboards/scripts/llms can operate on vault fundamentals instead of needing to parse and develop them from markdown at every step. Specs are always written to `readme.md` to better operate with github.

<!-- Folder structure -->
- `specs/` - individual files specifying systems and architectural components.
  - `server.md` - defines the server routes and functionality
  - `arch/` - individual files that identify a reusable architectural component, specify the interface for the component (how other systems use this component and the requirements that implementations have to satisfy). Individual implementation specs MUST refer to this template file so that we can maintain a consistent pattern
    - `routes.md` - defines the structure of a route spec (stored under `routes/`)
    - `database.md` - defines the structure of a database system spec (stored under `database/`)
  - `system/` - files that identify the individual system that the server exposes. These specs are basically intended to be referenced by implementation specs to provide context for terminology and references for system functionality
    - `routes.md`
  - `utils/` - helper files to specify utility functionality that is common to multiple systems but doesn't map to architectural templates. These basically map to `src/utils/`
- `src/` - the root folder for all generated code
  - `database/` - spec files describing database systems, data models, and interactions. Common database code and specs lie in the root while system-specific logic lies in per-system sub-folders. Effectively, each system defines a sub-folder that has the following files: `readme.md`, `model.py`, `query.py`
  - `routes/` - folder for the mcp/rest endpoints that we are exposing. for simplicity, we only define the mcp server and rely on fastmcp fastapi integration to generate the rest endpoint. Each system integration creates a sub-folder and each endpoint that that system exposes defines a unique sub-folder underneath the system folder. Each endpoint folder is 3 files: `readme.md` `route.py`, `test.py`. All `route.py` files under this folder are agglomerated into a single exposed mcp/rest server in `routes/server.py`
  - `vault/` - folder for all functionality that interacts with the obsidian vault, specifically the parsing and extraction logic for each system. Also contains logic for updating files, including debounce functionality to avoid frequent updating
  - `utils/` - various utilities that do not fit in the general patterns. Effectively these are just additional libraries