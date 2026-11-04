# Changelog

## 2026-11-04

- Prepared the first GitHub source snapshot with setup instructions for a fresh Windows checkout, example configuration files and automated checks. [Source snapshot](https://github.com/ZafarHussain223/MemoryVault-AI/commit/7a8ce16dd1229926945d0c48b09509f8d7576a0a)
- Verified the extracted source archive locally with a new SQLite database. All 151 API tests and 18 browser workflows passed, alongside TypeScript checking and the production build. These results apply to the source snapshot linked above.
- Added the MIT license and linked the README to current hosted build results. [GitHub Actions](https://github.com/ZafarHussain223/MemoryVault-AI/actions/workflows/checks.yml)

## 2026-10-30

- Added in-app original file viewing, private Office previews and section navigation for long documents. Upload and indexing tests cover PowerPoint slides, content beyond 20,000 words and a search result on the last page of a 330-page test PDF. [Document support](docs/DOCUMENT_SUPPORT.md)
- Fixed the desktop cursor switching back to the system pointer during scrolling. A browser test checks wheel scrolling while the pointer stays still. [Browser tests](apps/web/e2e/knowledge-design.spec.ts)
