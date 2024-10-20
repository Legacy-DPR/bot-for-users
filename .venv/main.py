import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('.env')

API_TOKEN = os.getenv("API_TOKEN")
USER_CHECK_URL = os.getenv("USER_CHECK_URL")
USER_REGISTER_URL = os.getenv("USER_REGISTER_URL")
MENU_URL = os.getenv("MENU_URL")
TICKET_URL = os.getenv("TICKET_URL")
SECRET_TOKEN = os.getenv("SECRET_TOKEN")
DEPARTMENTS_URL = os.getenv("DEPARTMENTS_URL")

bot = telebot.TeleBot(API_TOKEN)

user_state = {}
menus = {}
group_map = {}
operation_map = {}
departments = []
user_operation_id = {}

def send_operation_request(telegram_id, operation_id, department_id):
    appointed_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

    data = {
        "telegramId": str(telegram_id),
        "appointedTime": appointed_time,
        "operationId": operation_id,
        "departmentId": department_id
    }

    try:
        response = requests.post(TICKET_URL, json=data, headers={"Authorization": SECRET_TOKEN})
        if response.status_code == 201:
            print(f"Успешно отправлен запрос для операции {operation_id} в отделении {department_id}")
            return response.json().get("id")
        else:
            print(f"Ошибка при отправке запроса: {response.text}")
            print(f"Код ошибки: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при отправке запроса (исключение): {e}")
        return None

def get_ticket_info(ticket_id):
    try:
        response = requests.get(f"{TICKET_URL}/{ticket_id}", headers={"Authorization": SECRET_TOKEN})
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Ошибка получения информации о талоне: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении информации о талоне: {e}")
        return None

def transform_menu(data):
    global group_map, operation_map
    menu = {"main": []}

    for group in data:
        group_name = group["name"]
        group_map[group_name] = group["id"]

        menu["main"].append(group_name)
        menu[group["id"]] = []

        for operation in group["operations"]:
            op_name = operation["name"]
            operation_map[op_name] = operation["id"]
            menu[group["id"]].append(op_name)

    return menu

def load_menu():
    try:
        response = requests.get(MENU_URL, headers={"Authorization": SECRET_TOKEN})
        response.raise_for_status()
        return transform_menu(response.json())
    except requests.exceptions.RequestException as e:
        print(f"Ошибка загрузки меню: {e}")
        return {}

def get_department_operations(department_id):
    for department in departments:
        if department["id"] == department_id:
            available_group_names = []
            for group in department["availableOperationGroups"]:
                available_group_names.append(group["name"])
            return available_group_names
    return []

def create_keyboard(buttons, add_navigation=True):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    for button in buttons:
        keyboard.add(KeyboardButton(button))
    if add_navigation:
        keyboard.add(KeyboardButton('Главное меню'))
    return keyboard

def set_user_state(user_id, state):
    user_state[user_id] = state

def get_user_state(user_id):
    return user_state.get(user_id, "main")

def reset_to_main_menu(user_id):
    set_user_state(user_id, "main")
    bot.send_message(
        user_id, "Вы вернулись в главное меню.",
        reply_markup=create_keyboard(menus.get("main", []), add_navigation=False)
    )

def check_user_registration(telegram_id):
    try:
        response = requests.get(USER_CHECK_URL + str(telegram_id), headers={"Authorization": SECRET_TOKEN})
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"Ошибка проверки пользователя: {e}")
        return False

def register_user(telegram_id):
    data = {"telegramId": str(telegram_id)}
    try:
        response = requests.post(USER_REGISTER_URL, json=data, headers={"Authorization": SECRET_TOKEN})
        return response.status_code == 201
    except requests.exceptions.RequestException as e:
        print(f"Ошибка регистрации: {e}")
        return False

def load_departments():
    global departments
    try:
        response = requests.get(DEPARTMENTS_URL, headers={"Authorization": SECRET_TOKEN})
        response.raise_for_status()
        departments = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Ошибка загрузки отделений: {e}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = message.chat.id
    telegram_id = user_id

    if check_user_registration(telegram_id):
        global menus
        menus = load_menu()
        load_departments()
        reset_to_main_menu(user_id)
    else:
        if register_user(telegram_id):
            bot.send_message(user_id, "Регистрация завершена.")
            menus = load_menu()
            load_departments()
            reset_to_main_menu(user_id)
        else:
            bot.send_message(user_id, "Ошибка регистрации. Попробуйте позже.")

def format_date(appointed_time):
    dt = datetime.fromisoformat(appointed_time[:-1])
    return dt.strftime('%d %B %Y г., %H:%M:%S')

@bot.message_handler(func=lambda message: True)
def message_handler(message):
    user_id = message.chat.id
    current_state = get_user_state(user_id)

    if message.text == 'Главное меню':
        reset_to_main_menu(user_id)
        return

    if message.text in group_map:
        group_id = group_map[message.text]
        set_user_state(user_id, message.text)
        bot.send_message(
            user_id, f"Вы выбрали группу: {message.text}. Пожалуйста, выберите операцию.",
            reply_markup=create_keyboard(menus.get(group_id, []))
        )
    elif message.text in operation_map:
        operation_id = operation_map[message.text]
        user_operation_id[user_id] = operation_id

        bot.send_message(user_id, "Пожалуйста, выберите отделение:",
                         reply_markup=create_keyboard([dep["address"] for dep in departments]))
    elif message.text in [dep["address"] for dep in departments]:
        department_id = next(dep["id"] for dep in departments if dep["address"] == message.text)
        selected_group_name = get_user_state(user_id)
        operation_id = user_operation_id.get(user_id)

        available_group_names = get_department_operations(department_id)

        if selected_group_name in available_group_names:
            ticket_id = send_operation_request(user_id, operation_id, department_id)
            if ticket_id:
                ticket_info = get_ticket_info(ticket_id)
                if ticket_info:
                    operation_name = ticket_info['operation']['name']
                    department_address = ticket_info['department']['address']
                    appointed_time = format_date(ticket_info['appointedTime'])

                    bot.send_message(user_id, f"Талон успешно создан!\nID талона: {ticket_info['id']}\n"
                                              f"Операция: {operation_name}\n"
                                              f"Отделение: {department_address}\n"
                                              f"Время: {appointed_time}")
                else:
                    bot.send_message(user_id, "Не удалось получить информацию о талоне.")
            else:
                bot.send_message(user_id, "Не удалось создать талон.")
        else:
            bot.send_message(user_id, "Выбранное отделение не поддерживает эту операцию.")
    else:
        bot.send_message(user_id, "Я не понимаю вас. Пожалуйста, выберите доступный вариант.")

if __name__ == "__main__":
    bot.polling(none_stop=True)
