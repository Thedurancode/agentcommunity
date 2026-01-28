from typing import Optional, List, Dict, Any

from anthropic import AsyncAnthropic

from app.core.config import settings


class AIService:
    def __init__(self):
        if not settings.ANTHROPIC_API_KEY:
            self.client = None
        else:
            self.client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    def is_available(self) -> bool:
        return self.client is not None

    async def generate_recap_summary(
        self,
        project_name: str,
        recent_commits: List[Dict[str, Any]],
        recent_issues: List[Dict[str, Any]],
        recent_notes: List[Dict[str, Any]],
    ) -> str:
        """Generate an AI summary of recent project activity."""
        if not self.client:
            raise ValueError("AI service not configured. Set ANTHROPIC_API_KEY.")

        # Build context from recent activity
        commits_text = ""
        if recent_commits:
            commits_text = "Recent Commits:\n"
            for commit in recent_commits:
                commits_text += f"- {commit.get('message', 'No message')} by {commit.get('author', 'Unknown')}\n"

        issues_text = ""
        if recent_issues:
            issues_text = "Recent Issues:\n"
            for issue in recent_issues:
                state = issue.get('state', 'unknown')
                issues_text += f"- [{state}] {issue.get('title', 'No title')}\n"

        notes_text = ""
        if recent_notes:
            notes_text = "Recent Notes:\n"
            for note in recent_notes:
                creator = note.get('created_by', 'Unknown')
                notes_text += f"- {note.get('title', 'No title')} (by {creator})\n"

        prompt = f"""You are a helpful assistant that summarizes project activity for a development team.

Project: {project_name}

{commits_text}
{issues_text}
{notes_text}

Please provide a brief, professional summary (2-4 sentences) of the recent activity on this project. Focus on:
1. What work has been done (commits)
2. Current priorities or blockers (issues)
3. Any important team notes

Keep the tone informative and concise. If there's no activity in a category, don't mention it."""

        response = await self.client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=300,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        return response.content[0].text

    async def generate_issue_summary(
        self,
        issues: List[Dict[str, Any]],
    ) -> str:
        """Generate a summary of issues for a project."""
        if not self.client:
            raise ValueError("AI service not configured. Set ANTHROPIC_API_KEY.")

        issues_text = ""
        for issue in issues:
            state = issue.get('state', 'unknown')
            body = issue.get('body', '')[:200] if issue.get('body') else 'No description'
            issues_text += f"- [{state}] {issue.get('title', 'No title')}: {body}\n"

        prompt = f"""Summarize these project issues in 2-3 sentences, highlighting key themes and priorities:

{issues_text}

Be concise and focus on actionable insights."""

        response = await self.client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=200,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        return response.content[0].text

    async def suggest_next_steps(
        self,
        project_name: str,
        recent_commits: List[Dict[str, Any]],
        recent_issues: List[Dict[str, Any]],
        recent_notes: List[Dict[str, Any]],
    ) -> str:
        """Generate AI-suggested next steps for the project."""
        if not self.client:
            raise ValueError("AI service not configured. Set ANTHROPIC_API_KEY.")

        context = f"Project: {project_name}\n\n"

        if recent_commits:
            context += "Recent work:\n"
            for commit in recent_commits[:3]:
                context += f"- {commit.get('message', '')}\n"

        if recent_issues:
            open_issues = [i for i in recent_issues if i.get('state') == 'open']
            if open_issues:
                context += "\nOpen issues:\n"
                for issue in open_issues[:3]:
                    context += f"- {issue.get('title', '')}\n"

        if recent_notes:
            context += "\nRecent notes:\n"
            for note in recent_notes[:2]:
                context += f"- {note.get('title', '')}\n"

        prompt = f"""{context}

Based on this project activity, suggest 3 concrete next steps the team should consider. Be specific and actionable. Format as a numbered list."""

        response = await self.client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=300,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        return response.content[0].text

    async def organize_transcript(
        self,
        transcript: str,
        project_name: str,
    ) -> Dict[str, Any]:
        """
        Organize a voice transcript into structured notes and tasks.

        Returns:
            Dict with keys: summary, organized_notes (markdown), extracted_tasks (list)
        """
        if not self.client:
            raise ValueError("AI service not configured. Set ANTHROPIC_API_KEY.")

        prompt = f"""You are an expert project manager and technical writer. Analyze this voice transcript from a meeting/brainstorm about the project "{project_name}" and organize it into structured notes.

TRANSCRIPT:
{transcript}

Please provide:

1. **SUMMARY** (2-3 sentences): What is this transcript about?

2. **ORGANIZED NOTES** (markdown format):
   - Group related ideas under clear headings
   - Use bullet points for details
   - Highlight key decisions or insights
   - Clean up any verbal filler or repetition

3. **EXTRACTED TASKS** (as a JSON array):
   - Extract any action items, todos, or things that need to be built
   - Each task should have: "title", "description", "priority" (high/medium/low)
   - Be specific about what needs to be done

Format your response EXACTLY like this:

## SUMMARY
[Your summary here]

## ORGANIZED NOTES
[Your markdown notes here]

## EXTRACTED TASKS
```json
[
  {{"title": "Task title", "description": "What needs to be done", "priority": "high"}},
  ...
]
```"""

        response = await self.client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=4000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = response.content[0].text

        # Parse the response
        import json
        import re

        result = {
            "summary": "",
            "organized_notes": "",
            "extracted_tasks": []
        }

        # Extract summary
        summary_match = re.search(r'## SUMMARY\s*\n(.*?)(?=\n## |$)', response_text, re.DOTALL)
        if summary_match:
            result["summary"] = summary_match.group(1).strip()

        # Extract organized notes
        notes_match = re.search(r'## ORGANIZED NOTES\s*\n(.*?)(?=\n## EXTRACTED TASKS|$)', response_text, re.DOTALL)
        if notes_match:
            result["organized_notes"] = notes_match.group(1).strip()

        # Extract tasks JSON
        tasks_match = re.search(r'```json\s*\n(.*?)\n```', response_text, re.DOTALL)
        if tasks_match:
            try:
                result["extracted_tasks"] = json.loads(tasks_match.group(1))
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract tasks manually
                result["extracted_tasks"] = []

        return result


# Singleton instance
ai_service = AIService()


def get_ai_service() -> AIService:
    return ai_service
