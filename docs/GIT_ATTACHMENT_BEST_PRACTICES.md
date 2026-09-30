# `reqtool` -- Git Binary Attachment & Audit History Guide

---

## 1. Managing Binary Attachments in Git

Because `reqtool` is 100% Git-backed, managing binary attachments (images, PDFs, CAD schematics, wireframes) requires balancing version control transparency with repository size optimization.

### 1.1 Recommended Setup: Git LFS (Large File Storage)

To prevent binary file bloat in standard Git object databases while retaining full version control, `reqtool` repositories should configure **Git LFS** via `.gitattributes`.

Create or update `.gitattributes` in your repository root:

```ini
# .gitattributes -- reqtool Git LFS tracking for binary attachments
attachments/*/*.png  filter=lfs diff=lfs merge=lfs -text
attachments/*/*.jpg  filter=lfs diff=lfs merge=lfs -text
attachments/*/*.jpeg filter=lfs diff=lfs merge=lfs -text
attachments/*/*.gif  filter=lfs diff=lfs merge=lfs -text
attachments/*/*.pdf  filter=lfs diff=lfs merge=lfs -text
attachments/*/*.zip  filter=lfs diff=lfs merge=lfs -text
attachments/*/*.step filter=lfs diff=lfs merge=lfs -text
```

**Benefits:**
- Lightweight Git clones (`git clone` remains fast).
- Large media files are stored on Git LFS pointers natively supported by GitHub, GitLab, and Azure DevOps.
- Full binary version history is preserved per branch.

---

## 2. Audit Trail & Attachment Version History

In `reqtool`, attachment operations (add, update, replace, delete) are subject to the same strict audit control as requirement text changes.

### 2.1 Metadata & SHA-256 Tracking in Requirement YAML
Whenever an attachment is added, its metadata and cryptographic SHA-256 hash are recorded inside the requirement's YAML file (`requirements/<uid>.yaml`):

```yaml
id: REQ-SYS-001
title: Thermal Control System Enclosure
version: 1.2.0
attachments:
  - filename: enclosure_v2.png
    size_bytes: 452100
    sha256: a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0
    added_by: alice_engineer
    added_date: '2026-09-30T18:45:00Z'
    description: Enclosure revision 2 CAD render
```

### 2.2 Automatic Requirement Version Bump
In `reqtool`, uploading or deleting an attachment alters the requirement's content hash and triggers an automatic semantic version increment (`1.1.0` → `1.2.0`).

### 2.3 Git Audit Log & Historical Diffs
Every attachment operation generates an immutable Git commit:
```
commit a1b2c3d4
Author: Alice Smith <alice@example.com>
Date:   Wed Sep 30 18:45:00 2026

    feat(REQ-SYS-001): added attachment enclosure_v2.png
```

To inspect full audit history of attachments for any requirement:
- **CLI:** `reqtool diff HEAD~5`
- **REST API:** `GET /requirements/{uid}/history`
- **Regulatory Audit Exporter:** `GET /export/audit-package` includes `cryptographic_signatures.json` locking requirement text, author identities, and attachment SHA-256 hashes into the compliance dossier.
