import datetime as dt
from abc import ABC

from flask import jsonify, request

from pythia.exceptions import PythiaException, ValidationError


class Endpoint(ABC):
    disabled: bool = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Endpoint"):
            raise TypeError(
                f"Endpoint subclasses must end with 'Endpoint' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Endpoint'."
            )

        if getattr(cls, "disabled", False):
            return

        _required = ("url", "method", "mcp_definition", "callback")
        if all(vars(cls).get(attr) for attr in _required):
            cls()

    def _callback(self, **kwargs):
        try:
            data = request.get_json() or {}
            valid_params = self.mcp_definition.get("parameters", {}).get("properties", {})
            parameters = {}

            for key, value in data.items():
                if key not in valid_params:
                    raise ValidationError(f"Invalid parameter: {key}")
                parameters[key] = value

            for key, value in parameters.items():
                if isinstance(value, str) and key == "reference_date":
                    try:
                        dt_parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                        parameters[key] = dt_parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
                    except ValueError:
                        raise ValidationError(f"Invalid date format for reference_date: {value}")

            result = self.callback(**parameters)
            return jsonify({
                "tool": self.mcp_definition["name"],
                "result": result,
                "success": True,
            })

        except PythiaException as e:
            return jsonify({
                "error": e.message,
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": e.__class__.__name__,
            }), e.status_code

        except Exception as e:
            return jsonify({
                "error": str(e),
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": "InternalServerError",
            }), 500

    def __init__(self):
        from pythia.server import Server

        self.mcp_definition = getattr(self, "mcp_definition", None)
        if not self.mcp_definition:
            raise ValueError(f"{self.__class__.__name__}: mcp_definition is required")

        self.method = getattr(self, "method", None)
        if not self.method:
            raise ValueError(f"{self.__class__.__name__}: method is required")

        self.url = getattr(self, "url", None)
        if not self.url:
            raise ValueError(f"{self.__class__.__name__}: url is required")

        if not getattr(self, "callback", None):
            raise ValueError(f"{self.__class__.__name__}: callback is required")

        server = Server.get_instance()
        server.app.add_url_rule(
            self.url,
            self.mcp_definition["name"],
            self._callback,
            methods=[self.method],
        )
        server.register_url_handler(self)
