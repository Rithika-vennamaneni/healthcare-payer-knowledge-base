#!/bin/bash
# Script to push Healthcare Payer Knowledge Base to GitHub

echo "=========================================="
echo "Push to GitHub - Healthcare Knowledge Base"
echo "=========================================="

# Check if git is initialized
if [ ! -d .git ]; then
    echo "Initializing git repository..."
    git init
    echo "✓ Git initialized"
else
    echo "✓ Git repository already exists"
fi

# Check git status
echo ""
echo "Current git status:"
git status --short | head -20

# Add all files
echo ""
echo "Adding files to git..."
git add .

# Show what will be committed
echo ""
echo "Files staged for commit:"
git status --short | head -20

# Create commit
echo ""
read -p "Enter commit message (default: 'Initial commit - Healthcare Payer Knowledge Base'): " commit_msg
commit_msg=${commit_msg:-"Initial commit - Healthcare Payer Knowledge Base"}

git commit -m "$commit_msg"
echo "✓ Commit created"

# Ask for repository URL
echo ""
echo "=========================================="
echo "GitHub Repository Setup"
echo "=========================================="
echo ""
echo "Before continuing, create a new repository on GitHub:"
echo "1. Go to: https://github.com/new"
echo "2. Repository name: healthcare-payer-knowledge-base"
echo "3. Description: Automated healthcare payer rule extraction system with RAG chatbot"
echo "4. Keep it Public or Private (your choice)"
echo "5. DO NOT initialize with README (we already have one)"
echo ""
read -p "Press Enter when you've created the repository..."

echo ""
read -p "Enter your GitHub repository URL (e.g., https://github.com/username/repo.git): " repo_url

if [ -z "$repo_url" ]; then
    echo "❌ No repository URL provided"
    exit 1
fi

# Add remote
echo ""
echo "Adding remote repository..."
git remote remove origin 2>/dev/null  # Remove if exists
git remote add origin "$repo_url"
echo "✓ Remote added: $repo_url"

# Push to GitHub
echo ""
echo "Pushing to GitHub..."
git branch -M main
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ SUCCESS! Code pushed to GitHub"
    echo "=========================================="
    echo ""
    echo "Your repository: $repo_url"
    echo ""
    echo "Next steps:"
    echo "1. View your repo in browser"
    echo "2. Add collaborators if needed"
    echo "3. Set up GitHub Actions (optional)"
    echo "4. Configure branch protection (optional)"
else
    echo ""
    echo "❌ Push failed. Common issues:"
    echo "1. Check your GitHub credentials"
    echo "2. Verify repository URL is correct"
    echo "3. Ensure you have push access"
    echo ""
    echo "Try: git push -u origin main"
fi
