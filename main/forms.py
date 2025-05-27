from django import forms
from .models import Project, Activity, Task

class ProjectForm(forms.ModelForm):
    """Form for creating and updating projects"""
    class Meta:
        model = Project
        fields = ['name', 'description', 'status', 'priority', 'start_date', 'end_date', 'team']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

class ActivityForm(forms.ModelForm):
    """Form for creating and updating activities"""
    class Meta:
        model = Activity
        fields = ['title', 'description', 'start_date', 'end_date', 'status']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'required': True}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'required': True}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'title': forms.TextInput(attrs={'required': True}),
        }

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)
        # Set default status
        self.fields['status'].initial = 'planning'
        # Make fields required
        self.fields['title'].required = True
        self.fields['start_date'].required = True
        self.fields['end_date'].required = True
        self.fields['status'].required = True

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError("End date must be after start date")

        if self.project:
            if start_date and start_date < self.project.start_date:
                raise forms.ValidationError("Activity start date cannot be before project start date")
            if end_date and end_date > self.project.end_date:
                raise forms.ValidationError("Activity end date cannot be after project end date")

        return cleaned_data

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['name', 'description', 'completed', 'assignee']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        } 