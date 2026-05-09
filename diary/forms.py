from django import forms
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator

from diary.models import BattleRequest, DailyRecord, Moment



class SimpleUserCreationForm(forms.Form):
    username = forms.CharField(label="用户名", max_length=150)
    password1 = forms.CharField(label="密码", widget=forms.PasswordInput)
    password2 = forms.CharField(label="确认密码", widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("用户名已存在")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("两次输入的密码不一致")
        return cleaned_data

    def save(self):
        user = User(username=self.cleaned_data["username"])
        user.set_password(self.cleaned_data["password1"])
        user.save()
        return user

# ============ 密码修改表单 ============

class TeacherVerifyForm(forms.Form):
    """第一步：验证台协老师姓名"""
    username = forms.CharField(
        label="用户名",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "username", "autofocus": True}),
    )
    teacher_name = forms.CharField(
        label="台协老师姓名",
        max_length=64,
        widget=forms.TextInput(attrs={"autocomplete": "off", "placeholder": "请输入老师姓名"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username", "").strip()
        teacher_name = cleaned_data.get("teacher_name", "").strip()

        if not username or not teacher_name:
            return cleaned_data

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise forms.ValidationError("用户名不存在")

        # 验证台协老师姓名（不区分大小写）
        if teacher_name != "王朋":
            raise forms.ValidationError("台协老师姓名验证失败")

        cleaned_data["user"] = user
        return cleaned_data


class PasswordResetVerifyForm(forms.Form):
    """第三步：设置新密码"""
    new_password1 = forms.CharField(
        label="新密码",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="确认新密码",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_new_password2(self):
        password1 = self.cleaned_data.get("new_password1")
        password2 = self.cleaned_data.get("new_password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("两次输入的密码不一致")
        return password2


class DailyRecordForm(forms.ModelForm):
    # 黑八比分选择
    EIGHT_BALL_SCORE_CHOICES = [(i, str(i)) for i in range(0, 51)]
    score_for = forms.TypedChoiceField(
        choices=EIGHT_BALL_SCORE_CHOICES, coerce=int, label="我方得分"
    )
    score_against = forms.TypedChoiceField(
        choices=EIGHT_BALL_SCORE_CHOICES, coerce=int, label="对方得分"
    )

    # 追分得分选择：-100 ~ +100
    SCORE_CHOICES = [(i, str(i)) for i in range(-100, 101)]
    score = forms.TypedChoiceField(
        choices=SCORE_CHOICES, coerce=int, label="得分/积分"
    )

    # 评论长度限制
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": "2000"}),
        validators=[MaxLengthValidator(2000)],
        label="当天评论",
        help_text="最多2000字符",
    )

    class Meta:
        model = DailyRecord
        fields = [
            "game_type",
            "date",
            "opponent_name",
            "score_for",
            "score_against",
            "clear_in_count",
            "clear_boom_count",
            "score",
            "big_jin",
            "small_jin",
            "golden_nine",
            "foul_count",
            "comment",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "opponent_name": forms.TextInput(
                attrs={
                    "placeholder": "例如：张三",
                    "maxlength": "64",
                }
            ),
        }

    def clean_comment(self):
        """清理评论内容，移除潜在的危险字符"""
        comment = self.cleaned_data.get("comment", "")
        if comment:
            # 移除 HTML 标签防止 XSS
            import re
            comment = re.sub(r"<[^>]+>", "", comment)
            comment = comment.strip()
        return comment

    def clean_opponent_name(self):
        """清理对手名称"""
        name = self.cleaned_data.get("opponent_name", "")
        if name:
            import re
            # 只允许文字、数字、空格、常用标点
            name = re.sub(r"[^\w\s\u4e00-\u9fff\-\(\)\[\]]", "", name)
            name = name.strip()[:64]  # 限制长度
        return name




class BattleForm(forms.ModelForm):
    class Meta:
        model = BattleRequest
        fields = ["battle_time", "location", "player_count", "note"]
        widgets = {
            "battle_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "location": forms.TextInput(attrs={"maxlength": "120", "placeholder": "例如：学校台球厅"}),
            "player_count": forms.NumberInput(attrs={"min": "1", "max": "20"}),
            "note": forms.Textarea(attrs={"rows": 3, "maxlength": "500", "placeholder": "补充玩法、水平、联系方式等"}),
        }

    def clean_location(self):
        import re
        location = self.cleaned_data.get("location", "")
        location = re.sub(r"<[^>]+>", "", location).strip()[:120]
        if not location:
            raise forms.ValidationError("请填写地点")
        return location

    def clean_player_count(self):
        count = self.cleaned_data.get("player_count") or 1
        if count < 1:
            raise forms.ValidationError("寻找人数至少为1人")
        if count > 20:
            raise forms.ValidationError("寻找人数不能超过20人")
        return count

    def clean_note(self):
        import re
        note = self.cleaned_data.get("note", "")
        return re.sub(r"<[^>]+>", "", note).strip()[:500]

class MomentForm(forms.ModelForm):
    text = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "maxlength": "1000",
                "placeholder": "分享今天的台球瞬间...",
            }
        ),
        validators=[MaxLengthValidator(1000)],
        label="朋友圈内容",
    )

    class Meta:
        model = Moment
        fields = ["text"]

    def clean_text(self):
        text = self.cleaned_data.get("text", "")
        if text:
            import re
            text = re.sub(r"<[^>]+>", "", text).strip()
        return text


