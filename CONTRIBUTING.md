# Contributing

Thank you for looking. Before anything else, please read the safety notice in
the [README](README.md). **This is research work. It is not built for regular
use, and it is not a product.** If you are here to put it into service, this is
the wrong repository.

---

## What this repository is, and what it is not

This is the **publication** repository. It is filled with finished versions
only; it is not where day-to-day work happens. The working tree lives elsewhere
and contains real credentials, real device addresses and photographs of real
people — none of which can ever leave it.

That has one consequence you need to know about before you spend an evening on
a patch:

> **Pull requests are merged by hand into the working tree, not merged here.**

A change you contribute is read, adopted into the working tree, tested against
the bench there, and comes back out with the next published version. Your commit
will not appear in this repository's history under your name. That is not
ingratitude — it is the only honest way to run a repository whose upstream
cannot be published.

If that is not acceptable to you, say so before you write the patch, and we will
find another way. Nobody should discover this after the work.

---

## The licensing part, plainly

By submitting a contribution for inclusion in an official work, you license it
under the **Devious City License 1.0 or later** — the same terms as the rest of
the project. There is no separate contributor agreement to sign, and no
copyright assignment: **your work stays yours.**

This follows from §17 of the licence, and it is worth being precise about what
that section does and does not cover:

- It covers what you **submit for inclusion** — a pull request, a patch, a
  file you send along.
- It does **not** cover a public fork, an independently published modified
  version, a bug report, a feature request, a comment or a review. Those are
  not contributions in this sense, and nothing about them changes hands.

So: opening an issue commits you to nothing. Sending a patch licenses that
patch.

---

## Before you send something

**Say what it is for.** A patch whose purpose is clear gets read properly.
A patch that only says "fix" gets read last.

**Keep the reasoning.** This project's source carries the *why* in its comments,
not only the *what* — why a value is this one and not that one, what went wrong
the last time it was different. If your change replaces such a passage, replace
the reasoning too. A comment that has quietly become false is worse than no
comment.

**Run the bench.** The test scripts live outside this repository, but their
shape is described in the project documentation. Anything touching device
communication, calibration, the punishment channel or the version floor needs a
check that would have caught the mistake — and a **counter-proof** that the
check itself can fail. A test that passes no matter what is a test that proves
nothing.

**Do not add credentials, addresses or photographs.** Not even placeholders that
look real. The release tooling refuses to build a package that contains them,
and it refuses loudly.

---

## Safety-relevant changes

Some of this code decides how much current reaches a person's skin, how long a
magnet holds someone in place, and when a device is refused. If your change
touches any of that:

- Explain what the worst case is if you are wrong.
- Say what the change does when a message is lost, delayed, or arrives twice.
- Say what happens when the central unit goes away mid-action.

A change in these areas that cannot answer those three questions will not be
adopted, however clean the code is. This is not gatekeeping — it is the
difference between a bug and an injury.

---

## Language

Source comments, documentation in this repository and commit messages are
**English**. The project's internal documentation is German; that is not
published here.

Established loanwords stay as they are on both sides. It is a *bridge*, not a
*Brücke*.
