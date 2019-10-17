# queue-telegram-bot
Telegram bot on Aiogram for running lines with inline buttons

## Requirements
- Python 3.7
- modules from requirements.txt

## Database
SQLite is used for development purposes. Bot is compatible with really any serious database like PostgreSQL or MySQL. Connection string in database.py should be changed in order to use them.

## Commands

- /help
- /create [text] - creates queue in current chat that will be published after number of minutes set in /timer
- /delete - deletes queue. Only creator has access to do it. Message should be a reply to bot message with queue
- /timer - set number of minutes between creation and publication. Default is 60 minutes
- /pin - switch whether bot should pin published queues or not. Enabled by default.

## Other functionality

Users can add other users by replying to queue message with their username. Users can't add more than 1 other user. To-add user must use bot before at least once (he must be present in the database)
