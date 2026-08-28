"""Pydantic 兼容层"""

from pydantic import VERSION as PYDANTIC_VERSION

IS_V1 = PYDANTIC_VERSION.startswith("1.")
PYDANTIC_V2 = not IS_V1

if IS_V1:
    from pydantic import parse_obj_as, parse_raw_as  # type: ignore

    def model_rebuild(model):
        model.update_forward_refs()

    def type_validate_python(type_, data):
        return parse_obj_as(type_, data)

    def type_validate_json(type_, json_data):
        return parse_raw_as(type_, json_data)

    def model_dump(model):
        return model.dict()

    class ConfigDict:
        pass
else:
    from pydantic import TypeAdapter, ConfigDict

    def model_rebuild(model):
        model.model_rebuild()

    def type_validate_python(type_, data):
        return TypeAdapter(type_).validate_python(data)

    def type_validate_json(type_, json_data):
        return TypeAdapter(type_).validate_json(json_data)

    def model_dump(model):
        return model.model_dump()
