import logging
import time
import json
import flask
import telebot
import pandas as pd

import config
import chatbot.DialogueManagement as dm
import chatbot.NaturalLanguageGeneration as nlg
#from chatbot.NaturalLanguageUnderstanding import MoviePlot
#from chatbot.NaturalLanguageUnderstanding import NER

logger = telebot.logger
telebot.logger.setLevel(logging.DEBUG)
bot = telebot.TeleBot(config.TG_API_TOKEN, threaded=False)
app = flask.Flask(__name__)

@app.route('/', methods=['GET', 'HEAD'])
def index():
    return ''

@app.route(config.WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    if flask.request.headers.get('content-type') == 'application/json':
        json_string = flask.request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        flask.abort(403)

@app.route('/set_webhook', methods=['GET', 'POST'])
def set_webhook():
    bot.remove_webhook()
    time.sleep(0.1)
    bot.set_webhook(url=config.WEBHOOK_URL_BASE + config.WEBHOOK_URL_PATH,
                    certificate=open(config.WEBHOOK_SSL_CERT, 'r'))
    return ''

# Начало диалога
@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(message.chat.id, "Hello, " + message.from_user.first_name)
    bot.send_message(message.chat.id, "Please desctribe the movie you would like me to find")
    dm.set_state(message.chat.id, dm.States.S_SEARCH.value)

@bot.message_handler(commands=['help'])
def cmd_help(message):
    bot.send_message(message, "TODO")

@bot.message_handler(func=lambda message: dm.get_current_state(message.chat.id) == dm.States.S_SEARCH.value)
def user_entering_description(message):
    logger.debug("user_entering_description, message: " + message.text)
    decision = pipeline(message)
    if decision == dm.States.R_OK:
        print(dm.ApiDicts.genre_to_id)
        films = json.loads(dm.get_request(message.chat.id, message.message_id + 2))
        response = nlg.generateMarkdownMessage(films['results'][0], page=1)
        bot.send_message(message.chat.id, "I found something for you, hope you'll like it")
        bot.send_message(message.chat.id, response, 
                    disable_notification=True, reply_markup=get_markup(), parse_mode='Markdown')
    elif decision == dm.States.R_CLARIFY_GENRE:
        nlg.specifyGenre()
        dm.set_state(message.chat.id, dm.States.S_CLARIFY.value)
    elif decision == dm.States.R_CLARIFY_ALL:
        # Если не удалось найти фильм (или другое условие, по которому мы просим уточнить описание)
        bot.send_message(message.chat.id, "Please be more spectific with the description")
        dm.set_state(message.chat.id, dm.States.S_SEARCH.value)

@bot.message_handler(func= lambda message: dm.get_current_state(message.chat.id) == dm.States.S_CLARIFY.value)
def user_clarifying(message):
    logger.debug("user_clarifying, message: " + message.text)
    if pipeline(message):
        # Если получили положительный результат
        films = json.loads(dm.get_request(message.chat.id, message.message_id + 2))
        response = nlg.generateMarkdownMessage(films['results'][0], page=1)
        bot.send_message(message.chat.id, "I found something for you, hope you'll like it")
        bot.send_message(message.chat.id, response, 
                    disable_notification=True, reply_markup=get_markup(), parse_mode='Markdown')
        dm.set_state(message.chat.id, dm.States.S_SEARCH.value)
    else:
        # Если не получили уточнения, не меняем состояние
        bot.send_message(message.chat.id, "Please be more spectific with the description")

def pipeline(message):
    # Все нашли
    films = dm.api_discover(config.DB_API_TOKEN, genres=[28], actors=[117642])
    # Target message will be shifted by two : user_msg, found_msg, target_msg
    dm.save_request(message.chat.id, message.message_id + 2, films)
    dm.save_page(message.chat.id, message.message_id + 2, page=1)
    return dm.States.R_OK
    

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    current_page = dm.get_page(call.message.chat.id, call.message.message_id)
    new_page = current_page
    if call.data == "back":
        if current_page != 1:
            new_page -= 1
    elif call.data == "next":
        if current_page != 3:
            new_page += 1

    if current_page != new_page:
        dm.save_page(call.message.chat.id, call.message.message_id, new_page)
        films = json.loads(dm.get_request(call.message.chat.id, call.message.message_id))
        response = nlg.generateMarkdownMessage(films['results'][new_page - 1], page=new_page)
        bot.edit_message_text(response, call.message.chat.id, call.message.message_id,
                              reply_markup=get_markup(), parse_mode='Markdown')

def get_markup():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(telebot.types.InlineKeyboardButton("Back", callback_data=f"back"),
               telebot.types.InlineKeyboardButton("Next", callback_data=f"next"))
    return markup

if __name__ == "__main__":
    app.run()
