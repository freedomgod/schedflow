import pickle
from datetime import datetime
from zoneinfo import ZoneInfo

from schedflow.triggers import CronTrigger
from schedflow.utils import localize

tz = ZoneInfo("Europe/Berlin")

trigger = CronTrigger(
    month="5-8",
    day="6-15",
    end_date=localize(datetime(2017, 8, 10), tz),
)
# trigger = OrTrigger(
#     triggers=[
#         CronTrigger(
#             month="5-8",
#             day="6-15",
#             end_date=localize(datetime(2017, 8, 10), tz),
#         ),
#         CronTrigger(
#             month="6-9",
#             day="*/3",
#             end_date=localize(datetime(2017, 9, 7), tz),
#         ),
#     ]
# )

print(repr(trigger.end_date))
trigger2 = pickle.loads(pickle.dumps(trigger, protocol=pickle.HIGHEST_PROTOCOL))

print(repr(trigger2.end_date))


print(repr(localize(trigger2.end_date, trigger2.end_date.tzinfo)))


