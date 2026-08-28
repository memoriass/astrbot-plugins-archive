from ..core.types import Category, SubUnit, Tag, UserSubInfo
from ..database.db_manager import Subscription


def group_subscriptions(subs: list[Subscription]) -> list[SubUnit]:
    grouped: dict[str, list[Subscription]] = {}
    for sub in subs:
        grouped.setdefault(sub.uid, []).append(sub)

    sub_units = []
    for uid, sub_list in grouped.items():
        user_sub_infos = [
            UserSubInfo(
                user_id=sub.target_id,
                categories=[Category(c) for c in sub.categories],
                tags=[Tag(t) for t in sub.tags],
            )
            for sub in sub_list
        ]
        sub_units.append(SubUnit(sub_target=uid, user_sub_infos=user_sub_infos))
    return sub_units
