from aiogram.fsm.state import State, StatesGroup


class Flow(StatesGroup):
    city = State()
    category = State()
    date = State()
    price = State()
    subscription_city = State()
    subscription_category = State()
    subscription_period = State()
