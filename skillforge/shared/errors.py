"""统一异常体系。降级策略按异常类型分派，禁止字符串匹配。"""


class SkillForgeError(Exception):
    """所有 SkillForge 异常的基类。"""


class ConfigError(SkillForgeError):
    """配置缺失或格式非法。"""


class RouteAmbiguous(SkillForgeError):
    """路由命中多个技能，需要用户澄清。"""


class SkillNotFound(SkillForgeError):
    """请求的技能不存在。"""


class ContractViolation(SkillForgeError):
    """技能包契约字段缺失或非法。"""


class GateRejected(SkillForgeError):
    """门禁不通过且重写轮次用尽。"""


class RenderError(SkillForgeError):
    """渲染（docx 等）失败。"""
