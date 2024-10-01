EigenGen
========

EigenGen is a CLI Large Language Model frontend. It is geared towards working with code,
and supports a code review flow where you request changes and review patches suggested
by the tool similar to classic email based patch review.

EigenGen works with 
  - Anthropic claude-3-5-sonnet
  - OpenAI o1-preview, o1-mini, GPT4o
  - Google Gemini 1.5 pro 002
  - llama3.2:90b via Groq
  - Mistral Large v2

## Features

  - Basic prompt/answer flow with -p "Type your prompt here"
  - Diff output mode with -d that prints out the changes to files as a diff
  - Code Review flow with -r that gives you the option to continue discussing the changes with the LLM
    by typing your comments in-line with '> ' quoted diff. This is a bit like software development used to be before Pull Requests.
  - Add 'git ls-files' files to context automatically with -g, filtered by .eigengen_ignore.
  - eigengen -g --index creates an index cache in .eigengen_cache for semi-automatic context detection. When
    using -g switch after creating the index, eigengen includes any locally modified files as determined by git
    plus any files listed with -f argument, and then further adds those files that reference symbols defined in
    this list of files. Performance is good enough to work with pytorch repo, but linux kernel is still a bit too much,
    having a 12 second index cache load time. This would indicate that thousands of files are ok, but tens of thousands
    require patience. Rewriting the cache logic in C/C++/Rust/Zig would probably help but design must be validated
    more first.


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

## Tips

  - In addition to `eigengen` executable, we provide `egg` as well. It's shorter.
  - EigenGen uses `EDITOR` environment variable to pick the text editor.
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
# start a new code review flow to develop a TODO-list web app
eigengen -r -g -p "Please implement a TODO-list web app using react + javascript, thank you. Provide the full project directory structure, please. It should allow adding, editing and deleting entries."

# pipe file content in through stdin
cat setup.py | eigengen -f - -p "Please review the given source file, thank you!"

# pipe a git diff output and write a review for it
git diff origin/main^^..HEAD | eigengen -f - -p "Please write a code review for the given diff, thank you!
```

By default eigengen uses claude-3-5-sonnet. In order to use OpenAI GPT4o model, please give --model, -m argument
like this:
```
eigengen -m gpt4 -p "your prompt content"
```

You may wish to create a shell alias to avoid having to type it in all the time:
```
alias eigengen='eigengen -m gpt4'
```

## Work In Progress
  - HTTP API interface

## TODO:
  - ???
