# japanese-translation-workbench

[![CI](https://github.com/streerm/japanese-translation-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/streerm/japanese-translation-workbench/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A workbench for translating Japanese fiction into English with large language models.
Several models translate each passage independently; a strict segment-key protocol makes sure
no sentence is dropped, merged or left untranslated; a synthesis step drafts a combined version;
and a Streamlit grid lets a human translator compare, revise and finalise every segment before
exporting to Word.

> **Status:** under construction.
