from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect

from marketplace.models import HelpRequest

from .forms import DeveloperSignUpForm, UserUpdateForm


@csrf_protect
def signup(request):
    """Register a new user account and immediately authenticate the user."""
    if request.method == 'POST':
        form = DeveloperSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('home')
    else:
        form = DeveloperSignUpForm()

    return render(request, 'accounts/signup.html', {'form': form})


@login_required
def profile(request):
    """Render the authenticated user's dashboard with posts and accepted tasks."""
    context = {
        'my_posts': HelpRequest.objects.filter(user=request.user).order_by('-created_at'),
        'my_tasks': HelpRequest.objects.filter(accepted_by=request.user).order_by('-created_at'),
    }
    return render(request, 'accounts/profile.html', context)


@login_required
@csrf_protect
def edit_profile(request):
    """Update the authenticated user's email and bio details."""
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserUpdateForm(instance=request.user)

    return render(request, 'accounts/edit_profile.html', {'form': form})
