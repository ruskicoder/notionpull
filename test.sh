#!/bin/sh

FULL_TEST="https://your-notion-user.notion.site/Your-Test-Page-abc123"
NOTION_TEMPLATES="https://your-notion-user.notion.site/Your-Test-Page-templates-def456"
TINY_TEST="https://your-notion-user.notion.site/Your-Test-Page-tiny-ghi789"
PDF_TEST="https://your-notion-user.notion.site/Your-Test-Page-pdf-jkl012"

python3 notionpull -d -c $FULL_TEST > ./log.txt
