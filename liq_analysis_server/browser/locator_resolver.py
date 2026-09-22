class LocatorResolver:
    @staticmethod
    def resolve(page,spec):
        s=spec.model_dump() if hasattr(spec,"model_dump") else dict(spec or {}); by=s.get("by","css"); value=s.get("value","")
        if by=="css": loc=page.locator(value)
        elif by=="xpath": loc=page.locator(f"xpath={value}")
        elif by=="text": loc=page.get_by_text(value,exact=s.get("exact",False))
        elif by=="role": loc=page.get_by_role(s.get("role") or value,name=s.get("name") or None,exact=s.get("exact",False))
        elif by=="label": loc=page.get_by_label(value,exact=s.get("exact",False))
        elif by=="placeholder": loc=page.get_by_placeholder(value,exact=s.get("exact",False))
        elif by=="testid": loc=page.get_by_test_id(value)
        else: raise ValueError(f"지원하지 않는 locator다: {by}")
        return loc.nth(s["nth"]) if s.get("nth") is not None else loc

