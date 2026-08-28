[Fonts Installation Guide]

This plugin relies on local fonts to ensure text is rendered correctly in Docker environments, especially for Chinese characters.

Status:
- "Source Han Sans CN" (思源黑体 subset OTF) has been AUTO-DOWNLOADED. (Success!)
- Why Source Han Sans? It provides excellent Chinese support and we found a reliable mirror.
- We have aliased it to "Noto Sans SC" in the CSS, so no other code changes are needed.

Files currently present (should represent Chinese font):
- SourceHanSansCN-Regular.otf
- SourceHanSansCN-Bold.otf

If you still see boxes (tofu) for Chinese characters:
1. Verify the files above are ~8MB (Regular) and ~8MB (Bold).
2. Restart your bot to ensure the browser process reloads the fonts.

Manual Download Links (if auto-download corrupted):
   https://github.com/adobe-fonts/source-han-sans/raw/release/SubsetOTF/CN/SourceHanSansCN-Regular.otf
   https://github.com/adobe-fonts/source-han-sans/raw/release/SubsetOTF/CN/SourceHanSansCN-Bold.otf

Restart the bot after any changes.
