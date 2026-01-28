"""
Episode Generation Service

Generates TV show style episodes in "Pimp My Ride" format.
Each episode is 8 minutes total, broken into 2-minute segments.
"""
import json
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.episode import Episode
from app.models.episode_segment import EpisodeSegment, SegmentType
from app.models.project import Project
from app.schemas.episode_segment import GeneratedEpisodeStructure, GeneratedSegment


# Default 8-minute episode template (4 segments x 2 minutes each)
DEFAULT_SEGMENT_TEMPLATE = [
    {
        "segment_type": SegmentType.INTRO,
        "title": "The Problem",
        "description": "Introduction to the project and the challenge at hand",
        "duration_seconds": 120,
        "talking_points": [
            "Welcome to the show",
            "Meet the project owner",
            "What's broken or needs improvement?"
        ],
        "visual_notes": "Wide shot of the project, close-ups of problem areas",
        "music_cue": "Upbeat intro theme"
    },
    {
        "segment_type": SegmentType.TEAM_INTRO,
        "title": "Meet the Team",
        "description": "Introduce the team members who will tackle this challenge",
        "duration_seconds": 120,
        "talking_points": [
            "Who's on the team?",
            "What skills do they bring?",
            "Initial reactions to the challenge"
        ],
        "visual_notes": "Individual team member shots, quick interviews",
        "music_cue": "Energetic transition music"
    },
    {
        "segment_type": SegmentType.BUILD_MONTAGE,
        "title": "The Build",
        "description": "Watch the team work their magic",
        "duration_seconds": 120,
        "talking_points": [
            "Key technical decisions",
            "Challenges encountered",
            "Progress milestones"
        ],
        "visual_notes": "Fast-paced coding montage, whiteboard sessions, pair programming",
        "music_cue": "High-energy work music"
    },
    {
        "segment_type": SegmentType.REVEAL,
        "title": "The Reveal",
        "description": "Show off the finished product",
        "duration_seconds": 120,
        "talking_points": [
            "Demo the solution",
            "Project owner reaction",
            "What's next?"
        ],
        "visual_notes": "Dramatic reveal moment, demo walkthrough, celebration",
        "music_cue": "Triumphant reveal theme"
    }
]


def generate_episode_structure(
    episode_title: str,
    project_name: Optional[str] = None,
    project_description: Optional[str] = None,
    team_members: Optional[list] = None,
    issue_title: Optional[str] = None,
    issue_description: Optional[str] = None
) -> GeneratedEpisodeStructure:
    """
    Generate a TV show style episode structure based on project data.
    Returns a JSON-serializable structure with 4 segments totaling 8 minutes.
    """
    segments = []
    current_time = 0

    for i, template in enumerate(DEFAULT_SEGMENT_TEMPLATE):
        # Customize talking points based on available data
        talking_points = list(template["talking_points"])
        description = template["description"]

        if template["segment_type"] == SegmentType.INTRO:
            if project_name:
                talking_points[1] = f"Introducing: {project_name}"
            if issue_title:
                talking_points[2] = f"Today's challenge: {issue_title}"
            if project_description:
                description = f"Introduction to {project_name}: {project_description}"

        elif template["segment_type"] == SegmentType.TEAM_INTRO:
            if team_members and len(team_members) > 0:
                talking_points[0] = f"Meet the {len(team_members)} team members"
                member_names = [m.get("name", "Team Member") for m in team_members[:3]]
                talking_points[1] = f"Featuring: {', '.join(member_names)}"

        elif template["segment_type"] == SegmentType.BUILD_MONTAGE:
            if issue_description:
                talking_points[0] = f"Tackling: {issue_description[:100]}..."

        elif template["segment_type"] == SegmentType.REVEAL:
            if project_name:
                talking_points[0] = f"Presenting the new and improved {project_name}"

        segment = GeneratedSegment(
            segment_number=i + 1,
            segment_type=template["segment_type"],
            title=template["title"],
            description=description,
            start_time=current_time,
            duration_seconds=template["duration_seconds"],
            talking_points=talking_points,
            visual_notes=template["visual_notes"],
            music_cue=template["music_cue"]
        )
        segments.append(segment)
        current_time += template["duration_seconds"]

    return GeneratedEpisodeStructure(
        episode_title=episode_title,
        total_duration_seconds=current_time,
        segments=segments,
        project_name=project_name,
        project_description=project_description
    )


async def generate_episode_from_project(
    db: AsyncSession,
    episode_id: int,
    project_id: int
) -> GeneratedEpisodeStructure:
    """
    Generate episode structure from an existing project's data.
    Pulls in project info, team members, and recent issues.
    """
    # Get episode
    episode_result = await db.execute(
        select(Episode).where(Episode.id == episode_id)
    )
    episode = episode_result.scalar_one_or_none()
    if not episode:
        raise ValueError(f"Episode {episode_id} not found")

    # Get project with relationships
    from app.models.team_member import TeamMember
    project_result = await db.execute(
        select(Project)
        .options(selectinload(Project.team_members).selectinload(TeamMember.user))
        .options(selectinload(Project.issues))
        .where(Project.id == project_id)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Get team members as dict list (use username or full_name)
    team_members = [
        {"name": tm.user.full_name or tm.user.username, "role": tm.role.value}
        for tm in project.team_members
    ] if project.team_members else None

    # Get latest open issue as the "challenge"
    from app.models.issue import IssueState
    latest_issue = None
    if project.issues:
        open_issues = [i for i in project.issues if i.state == IssueState.OPEN]
        if open_issues:
            latest_issue = open_issues[0]

    return generate_episode_structure(
        episode_title=episode.title,
        project_name=project.name,
        project_description=project.description,
        team_members=team_members,
        issue_title=latest_issue.title if latest_issue else None,
        issue_description=latest_issue.body if latest_issue else None  # body not description
    )


async def create_segments_from_structure(
    db: AsyncSession,
    episode_id: int,
    structure: GeneratedEpisodeStructure
) -> list[EpisodeSegment]:
    """
    Create actual EpisodeSegment records from a generated structure.
    """
    segments = []

    for seg in structure.segments:
        segment = EpisodeSegment(
            episode_id=episode_id,
            segment_number=seg.segment_number,
            segment_type=seg.segment_type,
            title=seg.title,
            description=seg.description,
            start_time=seg.start_time,
            duration_seconds=seg.duration_seconds,
            talking_points=json.dumps(seg.talking_points),
            visual_notes=seg.visual_notes,
            music_cue=seg.music_cue
        )
        db.add(segment)
        segments.append(segment)

    await db.commit()

    # Refresh to get IDs
    for segment in segments:
        await db.refresh(segment)

    return segments
