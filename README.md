EigenGen
========

EigenGen is a CLI Large Language Model frontend. It is designed for working with code.
EigenGen uses a two-stage process where larger LLM is used to solve the task and produce
dense output, which is then given to a smaller LLM which applies the changes and produces
the complete file output. Finally this is then used to produce diffs which the user can choose to apply.

### Supported Models
EigenGen currently works correctly with:
  - OpenAI o1-preview, o1-mini, GPT4o (/meld by gpt-4o-mini)
  - Anthropic claude-3-5-sonnet (uses same model for /meld operation, haiku has too low output token limit)
  - llama3.2:90b via Groq (/meld by llama3.1-70b-versatile)
  - Google Gemini 1.5 pro 002 (/meld by gemini-1.5-flash-002 )
  - Mistral Large v2 (/meld uses the same)

Note: Mistral Large seems to have some trouble working with the EigenGen prompting. Similar issues happen
with all Mistral models regardless of size. Perhaps they require some distinctly different approach.

## Features

  - Basic prompt/answer flow with -p "Type your prompt here".
  - --chat mode allows discussing the changes and when the assistant answers with code blocks of changes,
    they can be applied with '/meld' command.
  - Add 'git ls-files' files to context automatically with -g, filtered by .eigengen_ignore.
  - eigengen -g --index creates an index cache in ~/.eigengen/cache for semi-automatic context detection. When
    using -g switch after creating the index, eigengen includes any locally modified files as determined by git
    plus any files listed with -f argument, and then further adds those files that reference symbols defined in
    this list of files.


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
```

## Configuration

You can place and adapt the following in $HOME/.eigengen/config.json
```
{
    "model": "o1-mini",
    "editor": "subl -w",
    "color_scheme": "solarized-dark"
}
```

These can be overriden with command line options.

## Tips

  - In addition to `eigengen` executable, we provide `egg` as well. It's shorter.
  - EigenGen can use `EDITOR` environment variable to pick the text editor.
  - Combining the two, for Sublime Text you can: `alias egg='EDITOR="subl -w" egg -m gpt4'`
  - Or if you're into VSCode: `alias egg='EDITOR="code -w" egg -m gpt4'`.
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
eigengen -g --chat -p "Please implement a TODO-list web app using react + javascript, thank you. Provide the full project directory structure, please. It should allow adding, editing and deleting entries."
```

By default eigengen uses claude-3-5-sonnet. In order to use OpenAI GPT4o model, please give --model, -m argument
like this:
```
eigengen -m gpt4 -p "your prompt content"
```

## Work In Progress
  - Exploring user interaction concepts

## TODO:
  - Add progress indicator as the LLM calls can take a very long time
