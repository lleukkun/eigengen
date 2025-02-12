EigenGen
========

EigenGen is a CLI Large Language Model frontend. It is designed for working with code.
Changes are presented to user as unified diffs for review before applying.

### Supported Models
EigenGen currently works correctly with:
  - DeepSeek deepseek-r1 (/meld by v3)
  - OpenAI o3-mini, o1 (/meld by gpt-4o-mini)
  - Anthropic claude-3-5-sonnet (uses same model for /meld operation)
  - deepseek-r1:70b via Groq (/meld by same)
  - Google gemini-2.0-flash-thinking-exp (/meld by gemini-2.0-flash-exp)
  - Mistral Large v2 (/meld uses the same)

## Features

  - --chat mode allows discussing the changes and when the assistant answers with code blocks,
    they can be applied with '/meld' command.
  - -d -p "your prompt" will give you a diff of the changes printed to stdout
  - -f [files...] allows you to specify the context to use



## Installation
```
pip install eigengen
```

You must export your API key using:
```
export ANTHROPIC_API_KEY=<your-api-key>
or
export OPENAI_API_KEY=<your-api-key>
or
export GROQ_API_KEY=<your-api-key>
or
export GOOGLE_API_KEY=<your-api-key>
or
export MISTRAL_API_KEY=<your-api-key>
or
export DEEPSEEK_API_KEY=<your-api-key>
```

## Configuration

You can copy `docs/sample-config.json` to your `$HOME/.eigengen/config.json` and edit the settings.
Supported color schemes are everything from [pygments](https://pygments.org/styles/).

## Tips

  - In addition to `eigengen` executable, we provide `egg` as well. It's shorter.
  - EigenGen can use `EDITOR` environment variable to pick the text editor.
  - Combining the two, for Sublime Text you can: `alias egg='EDITOR="subl -w" egg -m o3-mini'`
  - Or if you're into VSCode: `alias egg='EDITOR="code -w" egg -m o3-mini'`.
  - Vim/Neovim/Emacs users can probably figure out their own solutions.
  - Paths above are for Linux. MacOS and Windows binaries may not be in PATH, so you need to find them first.

## Development

Please install in edit mode like this:
```
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

For testing install pytest.


## Example Usage

```
# start a new chat pre-filling initial message from the command line
eigengen --chat -p "Please implement a TODO-list web app using react + javascript, thank you. Provide the full project directory structure, please. It should allow adding, editing and deleting entries."
```

By default eigengen uses claude-3-5-sonnet. In order to use OpenAI o3-mini model, please give --model, -m argument
like this:
```
eigengen -m o3-mini -p "your prompt content"
```

## Work In Progress
  - testing and cleanups

## TODO:
  - Fix tests
  - Context construction requires a lot more work. Goal is to be able to work with linux kernel sized projects.
