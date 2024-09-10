EigenGen
========

EigenGen is a command line driven code generator. It works with Anthropic claude-3-5-sonnet for now.

You must
```
export ANTHROPIC_API_KEY=<your-api-key>
```

and then create a venv and install this package with:
```
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Example Usage:
```
eigengen --diff --file eigengen/eigengen.py "Add OpenAI API support for gpt4o model, please!" | patch -p1
```

Pull Requests are welcome!
