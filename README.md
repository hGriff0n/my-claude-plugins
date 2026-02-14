# my-claude-plugins
Small repository to host the plugins I am making for my Claude Code personal assistant

1. effort-workflow
    - Basic scripts for creating and managing efforts within an obsidian vault
2. task-workflow
    - System for creating and managing tasks in a consistent recursive manner
3. review
    - Command for walking through pre-defined review sessions from a markdown file
4. daily
    - Commands for dealing with saving session information to daily files
5. windows
    - Skill for spawning claude sessions from claude

## Install

```
/plugin marketplace add hgriff0n/my-claude-plugins
/plugin install effort-workflow@my-claude-plugins
/plugin install task-workflow@my-claude-plugins
/plugin install review@my-claude-plugins
/plugin install daily@my-claude-plugins
/plugin install windows@my-claude-plugins
```

NOTE: `windows` skill requires user to configure windows terminal with a `claudeclone` profile. This profile can simply be a copy of your default profile but adding the equivalent of "-c claude" to the commandline. This gets around the issues with Claude Code not allowing for spawning new instances of Claude Code from Claude Code.