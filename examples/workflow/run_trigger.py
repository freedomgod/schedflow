from datetime import datetime
from schedflow.triggers import CronTrigger


if __name__ == '__main__':
    c = CronTrigger(
        {
            'second': 10,
            'minute': '*/2'
        }
    )
    print(c)
    prev = datetime(2025, 7, 19, 13, 3, 10)
    print(c.get_next_fire_time(prev, datetime.now()))
