─────────────────────────────────────────────
Title: LLM Context Construction System for Source Code
─────────────────────────────────────────────

1. Objective
 • Create a system that, given a large codebase (thousands of files), extracts and filters tokens to build a highly targeted context for LLM prompts.
 • Ensure that only tokens (from code and comments) that appear in fewer than 10 files are considered, thereby emphasizing specificity.

2. System Architecture
 • The system should be composed of modular components to allow independent development, testing, and potential future adjustments.
 • Main modules:
  a. File Parser and Token Extractor
  b. Inverted Index Builder
  c. Frequency Filter
  d. Context Extractor/Aggregator
  e. API/Interface for LLM Integration

3. Module Specifications

A. File Parser and Token Extractor
 • Input: Source files (all languages and file types as required).
 • Responsibilities:
  – Parse and tokenize each source file using language-aware parsers.
  – Extract tokens from both code (identifiers, literals) and natural language in comments.
  – Preserve exact token forms; differentiate common keywords (class, def, etc.) from unique identifiers.
 • Output: A stream or collection of tokens tagged with source file references and their positions (optional, for later snippet extraction).

B. Inverted Index Builder
 • Input: Tokenized data from the previous step.
 • Responsibilities:
  – Construct an inverted index mapping each unique token to a list of files where it appears.
  – Support efficient lookups by token.
 • Output: Data structure (e.g., hash map/dictionary) where key=token and value=list of file identifiers.

C. Frequency Filter
 • Input: Inverted Index.
 • Responsibilities:
  – Compute the occurrence count (document frequency) for each token.
  – Filter and retain only those tokens that appear in fewer than 10 files.
  – Optionally allow configuration (e.g., threshold value) for flexibility.
 • Output: A filtered set/index of “rare” tokens with associated file lists.

D. Context Extractor/Aggregator
 • Input: A specific target file for which the LLM context is being constructed and the filtered token index.
 • Responsibilities:
  – From the target file, identify all tokens that meet the “rare” criteria.
  – For each rare token in the target file, use the filtered inverted index to retrieve other related files.
  – Extract relevant code snippets or context blocks (e.g., surrounding token occurrences, function definitions, comment blocks) where the token appears.
  – Aggregate these snippets into a coherent, concise context that can be included in an LLM prompt.
  – Ensure the aggregation prioritizes tokens that are the most specific (e.g., tokens appearing only in 1-2 files).
 • Output: A composite context document (or structured JSON) ready for LLM processing.

E. API/Interface for LLM Integration
 • Responsibilities:
  – Provide an interface (e.g., RESTful API or command-line tool) to accept a target file and return the constructed LLM context.
  – Allow configuration of parameters such as the rarity threshold or snippet context length.
  – Ensure efficient query response times, possibly utilizing caching for large codebases.

4. Performance and Scalability Considerations
 • Precompute token frequencies and build the inverted index during an initialization or batch process.
 • Cache the results so that context constructions for individual files are fast.
 • Optimize each module to handle large codebases by using efficient data structures and, if necessary, parallel processing.

5. Deployment and Extensibility
 • The system should be containerized (e.g., Docker) to simplify deployment and scaling.
 • Document integration points so that additional context processing (e.g., secondary thresholds or fuzzy matching in the future) can be added modularly.

6. Testing and Validation
 • Write unit tests for each module, ensuring correct token extraction, index building, filtering, and snippet aggregation.
 • Validate with a sample subset of the codebase to verify that only tokens occurring in fewer than 10 files are selected and that related file contexts are meaningful.
 • Iterate on thresholds and snippet extraction logic based on developer and user feedback.

