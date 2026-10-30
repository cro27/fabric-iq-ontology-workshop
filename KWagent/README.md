# Fabric Ontology Agent

Interactive Python CLI agent built on the [Microsoft Agent Framework][maf]
that answers natural-language questions over a Microsoft Fabric ontology by
calling the ontology's MCP endpoint.

## Setup

```powershell
cd c:\FabricAgents\KWontologyAgent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # edit if needed
```

## Run

Sign in once with the Azure CLI (this is the interactive browser step):

```powershell
az login
# optional: az login --tenant <tenant-id>
```

Then start the agent:

```powershell
python agent.py
```

The cached CLI identity is used to acquire:

- a Fabric token (`https://api.fabric.microsoft.com/.default`) for the MCP
  server, and
- a Foundry project token to call the chat model.

Make sure your account has access to:

- the Fabric workspace `<workspace id>` and ontology
  item `<ontology id>`, and
- the Foundry project `<project name>` with the `<model>` deployment.

Type `exit` to quit.

[maf]: https://github.com/microsoft/agent-framework
