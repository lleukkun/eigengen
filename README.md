EigenGen
========

EigenGen is a CLI Large Language Model frontend. It is geared towards working with code,
and supports an --interactive mode that allows editing the produced diff before applying.
EigenGen works with 
  - Anthropic claude-3-5-sonnet
  - OpenAI GPT4o
  - llama3.1:70b by Groq


Installation:
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
```

For development please do something like:
```
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Example Usage:
```
# add new review feature using interactive mode
eigengen --interactive --diff --files eigengen/eigengen.py "Add --review flag and make it write a code review for the file given with --files argument. Please implement this by having --review fill in a default prompt with text 'Please write a code review for the given file'. --review should not be used together with --diff flag."

# pipe file content in through stdin
cat setup.py | eigengen -f - "Please review the given source file, thank you!"

# pipe a git diff output and write a review for it
git diff origin/main^^..HEAD | eigengen -f - "Please write a code review for the given diff, thank you!
```

By default eigengen uses claude-3-5-sonnet. In order to use OpenAI GPT4o model, please give --model-alias argument
like this:
```
eigengen --model-alias gpt4 "your prompt content"
```

You may wish to create a shell alias to avoid having to type it in all the time:
```.bashrc
alias eigengen='eigengen --model-alias gpt4'
```


TODO:
  - Figure out why Mistral's models just hate our system prompts.
  - Add some kind of directory indexing machinery to lessen the need to list files manually.

