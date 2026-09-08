# Contributing to AI Career Agent

This project is currently maintained by Vijay Shrivastava as a personal AI career automation tool. Contributions are welcome through issues and pull requests.

## Code of Conduct

* Be respectful and constructive.
* Prioritize user safety, privacy, and legal compliance.
* Do not propose features that bypass CAPTCHA, MFA, rate limits, anti-bot protections, or website terms.

## How to Contribute

1. **Open an issue** describing the bug or feature.
2. **Fork the repository** and create a branch from `main`.
3. **Implement** the change following the [Development Guidelines](DEVELOPMENT_GUIDELINES.md).
4. **Test** your change locally.
5. **Open a pull request** linking the issue.

## Branch Naming

* `feature/<short-desc>` — new features.
* `bugfix/<short-desc>` — bug fixes.
* `docs/<short-desc>` — documentation only.
* `security/<short-desc>` — security improvements.
* `chore/<short-desc>` — maintenance tasks.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat: add candidate skill proficiency field
fix: correct resume version lookup
docs: update ADR for LLM provider
security: enforce approval before outreach send
chore: bump dependency versions
```

## Pull Request Checklist

* [ ] Code follows project style and guidelines.
* [ ] Tests added or updated.
* [ ] Documentation updated if needed.
* [ ] No secrets or credentials committed.
* [ ] ADR added for any new major technology choice.
* [ ] Security implications considered.
* [ ] CI checks pass.

## Review Process

* All PRs require at least one review.
* Squash or merge commits may be used depending on the change scope.
* Security-sensitive changes require explicit approval.

## Reporting Security Issues

Do not open public issues for security vulnerabilities. Email or contact the project owner directly with details.

## Questions

Open a discussion issue or refer to the documentation in `/docs`.
