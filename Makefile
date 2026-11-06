.PHONY: test preview run editor

test:
	python3 -m unittest discover -s tests -v

preview:
	python3 tools/preview_themes.py docs/themes

run:
	python3 -m turmo_display

editor:
	python3 -m turmo_display.webapp
