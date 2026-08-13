"""Form widgets used across config (e.g. setup + auth admin)."""

from django import forms


class TeamMemberPickerWidget(forms.Widget):
    """
    Hidden value for ModelChoiceField + search + checkbox list (AJAX, team roster only).
    Pass attrs: data_search_url, data_for_user, data_initial_id, data_initial_label
    (underscores render as data-* hyphen attributes on the wrapper in templates).
    """

    template_name = "admin/widgets/team_member_picker.html"

    class Media:
        js = ("config/team_member_picker.js",)

    def value_from_datadict(self, data, files, name):
        is_multiple = str(self.attrs.get("data_multiple", "0")).lower() in {
            "1",
            "true",
            "yes",
        }
        if is_multiple and hasattr(data, "getlist"):
            return data.getlist(name)
        return data.get(name)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        wattrs = context.get("widget", {}).get("attrs", {}) or {}
        is_multiple = str(wattrs.get("data_multiple", "0")).lower() in {
            "1",
            "true",
            "yes",
        }
        initial_ids = wattrs.get("data_initial_ids", "")
        if is_multiple and not initial_ids:
            if isinstance(value, (list, tuple)):
                initial_ids = ",".join(str(v) for v in value if v not in (None, ""))
            elif value not in (None, ""):
                initial_ids = str(value)
        context["tm_search_url"] = wattrs.get("data_search_url", "")
        context["tm_for_user"] = wattrs.get("data_for_user", "")
        context["tm_is_multiple"] = is_multiple
        context["tm_initial_ids"] = initial_ids
        context["tm_initial_id"] = wattrs.get("data_initial_id", "")
        context["tm_initial_label"] = wattrs.get("data_initial_label", "")
        context["tm_search_placeholder"] = wattrs.get(
            "data_search_placeholder", "Search…"
        )
        context["tm_search_aria"] = wattrs.get("data_search_aria", "Search")
        context["tm_search_help"] = wattrs.get(
            "data_search_help",
            "Type to search. Results load from the server.",
        )
        context["tm_clear_label"] = wattrs.get("data_clear_label", "Clear selection")
        context["tm_empty_text"] = wattrs.get(
            "data_empty_text",
            "No matches found. Try another search.",
        )
        context["tm_error_text"] = wattrs.get(
            "data_error_text",
            "Could not load results. Try again.",
        )
        return context
