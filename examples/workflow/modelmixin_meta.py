from pydantic import BaseModel
from dataclasses import dataclass
from typing import Optional
from datetime import date
import pickle
from pydantic import (
    BaseModel, Field, ConfigDict, model_validator, field_serializer
)
from datetime import datetime, timedelta
from datetime import datetime, tzinfo
import random
from datetime import datetime, timedelta
from math import ceil
from typing import Optional, Mapping, Dict, Any
from tzlocal import get_localzone
from datetime import datetime, tzinfo

from pydantic import (
    BaseModel, Field, ConfigDict, model_validator, field_serializer, ValidationError
)
from schedflow.utils import (
    astimezone,
    convert_to_datetime,
    convert_to_date,
    datetime_repr,
)
from schedflow.triggers import IntervalTrigger, DateTrigger, CronTrigger, OrTrigger, CronTriggerModel
from schedflow.utils import localize



from zoneinfo import ZoneInfo

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


