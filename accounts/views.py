from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import DeveloperSignUpForm, UserUpdateForm
from marketplace.models import HelpRequest


def signup(request):
    if request.method == 'POST':
        form = DeveloperSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = DeveloperSignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})


@login_required
def profile(request):
    my_posts = HelpRequest.objects.filter(user=request.user).order_by('-created_at')
    my_tasks = HelpRequest.objects.filter(accepted_by=request.user).order_by('-created_at')

    context = {
        'my_posts': my_posts,
        'my_tasks': my_tasks,
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def edit_profile(request):
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('profile')
    else:
        form = UserUpdateForm(instance=request.user)
    return render(request, 'accounts/edit_profile.html', {'form': form})
