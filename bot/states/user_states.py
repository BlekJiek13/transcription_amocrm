from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    CHOOSING_LANGUAGE = State()
    CHOOSING_SUMMARY_STYLE = State()
    MAIN_SETTINGS_MENU = State()
