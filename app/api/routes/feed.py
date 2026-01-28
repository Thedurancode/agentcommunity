from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.project import Project
from app.models.team_member import TeamMember
from app.models.post import Post, PostComment, PostLike, PostSave, CommentLike, PostVisibility
from app.schemas.post import (
    PostCreate,
    PostUpdate,
    PostResponse,
    PostWithDetails,
    PostList,
    PostCommentCreate,
    PostCommentUpdate,
    PostCommentResponse,
    PostCommentWithAuthor,
    LikeResponse,
    SaveResponse,
    FeedResponse,
)
from app.schemas.user import UserResponse

router = APIRouter(prefix="/feed", tags=["feed"])


async def get_user_project_ids(db: AsyncSession, user_id: int) -> List[int]:
    """Get list of project IDs the user has access to."""
    result = await db.execute(
        select(TeamMember.project_id).where(TeamMember.user_id == user_id)
    )
    team_project_ids = [row[0] for row in result.fetchall()]

    result = await db.execute(
        select(Project.id).where(Project.owner_id == user_id)
    )
    owned_project_ids = [row[0] for row in result.fetchall()]

    return list(set(team_project_ids + owned_project_ids))


def post_to_response(post: Post, user_id: int) -> PostWithDetails:
    """Convert Post model to PostWithDetails response."""
    is_liked = any(like.user_id == user_id for like in post.likes)
    is_saved = any(save.user_id == user_id for save in post.saves)

    # Get recent comments (top 3)
    recent_comments = []
    for comment in sorted(post.comments, key=lambda c: c.created_at, reverse=True)[:3]:
        if comment.parent_id is None:  # Only top-level comments
            comment_liked = any(like.user_id == user_id for like in comment.likes)
            recent_comments.append(PostCommentWithAuthor(
                id=comment.id,
                post_id=comment.post_id,
                author_id=comment.author_id,
                parent_id=comment.parent_id,
                content=comment.content,
                likes_count=comment.likes_count,
                created_at=comment.created_at,
                updated_at=comment.updated_at,
                author=UserResponse.model_validate(comment.author),
                is_liked=comment_liked,
                replies=[],
            ))

    return PostWithDetails(
        id=post.id,
        author_id=post.author_id,
        project_id=post.project_id,
        content=post.content,
        media=post.media,
        visibility=post.visibility,
        likes_count=post.likes_count,
        comments_count=post.comments_count,
        saves_count=post.saves_count,
        created_at=post.created_at,
        updated_at=post.updated_at,
        author=UserResponse.model_validate(post.author),
        is_liked=is_liked,
        is_saved=is_saved,
        recent_comments=recent_comments,
    )


# Feed endpoints
@router.get("", response_model=FeedResponse)
async def get_feed(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    project_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the news feed for the current user."""
    user_project_ids = await get_user_project_ids(db, current_user.id)

    # Build visibility filter
    visibility_filter = or_(
        Post.visibility == PostVisibility.PUBLIC,
        Post.author_id == current_user.id,
        and_(
            Post.visibility == PostVisibility.PROJECT,
            Post.project_id.in_(user_project_ids) if user_project_ids else False
        )
    )

    query = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.likes),
        selectinload(Post.saves),
        selectinload(Post.comments).selectinload(PostComment.author),
        selectinload(Post.comments).selectinload(PostComment.likes),
    ).where(visibility_filter)

    if project_id:
        query = query.where(Post.project_id == project_id)

    query = query.order_by(Post.created_at.desc()).offset(skip).limit(limit + 1)

    result = await db.execute(query)
    posts = result.scalars().all()

    has_more = len(posts) > limit
    posts = posts[:limit]

    return FeedResponse(
        posts=[post_to_response(post, current_user.id) for post in posts],
        has_more=has_more,
    )


@router.get("/saved", response_model=PostList)
async def get_saved_posts(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get posts saved by the current user."""
    query = (
        select(Post)
        .join(PostSave, PostSave.post_id == Post.id)
        .options(
            selectinload(Post.author),
            selectinload(Post.likes),
            selectinload(Post.saves),
            selectinload(Post.comments).selectinload(PostComment.author),
            selectinload(Post.comments).selectinload(PostComment.likes),
        )
        .where(PostSave.user_id == current_user.id)
        .order_by(PostSave.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    posts = result.scalars().all()

    count_result = await db.execute(
        select(func.count(PostSave.id)).where(PostSave.user_id == current_user.id)
    )
    total = count_result.scalar()

    return PostList(
        posts=[post_to_response(post, current_user.id) for post in posts],
        total=total,
        has_more=(skip + limit) < total,
    )


@router.get("/user/{user_id}", response_model=PostList)
async def get_user_posts(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get posts by a specific user."""
    user_project_ids = await get_user_project_ids(db, current_user.id)

    # Build visibility filter for viewing other user's posts
    if user_id == current_user.id:
        visibility_filter = True  # Can see all own posts
    else:
        visibility_filter = or_(
            Post.visibility == PostVisibility.PUBLIC,
            and_(
                Post.visibility == PostVisibility.PROJECT,
                Post.project_id.in_(user_project_ids) if user_project_ids else False
            )
        )

    query = (
        select(Post)
        .options(
            selectinload(Post.author),
            selectinload(Post.likes),
            selectinload(Post.saves),
            selectinload(Post.comments).selectinload(PostComment.author),
            selectinload(Post.comments).selectinload(PostComment.likes),
        )
        .where(Post.author_id == user_id, visibility_filter)
        .order_by(Post.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    posts = result.scalars().all()

    count_query = select(func.count(Post.id)).where(Post.author_id == user_id, visibility_filter)
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return PostList(
        posts=[post_to_response(post, current_user.id) for post in posts],
        total=total,
        has_more=(skip + limit) < total,
    )


# Post CRUD
@router.post("/posts", response_model=PostWithDetails, status_code=status.HTTP_201_CREATED)
async def create_post(
    post_data: PostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new post."""
    # Verify project access if project_id provided
    if post_data.project_id:
        result = await db.execute(
            select(Project).where(Project.id == post_data.project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        # Check access
        if project.owner_id != current_user.id and current_user.role != "admin":
            member_result = await db.execute(
                select(TeamMember).where(
                    TeamMember.project_id == post_data.project_id,
                    TeamMember.user_id == current_user.id
                )
            )
            if not member_result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this project")

    post = Post(
        author_id=current_user.id,
        project_id=post_data.project_id,
        content=post_data.content,
        media=post_data.media.model_dump() if post_data.media else None,
        visibility=post_data.visibility,
    )

    db.add(post)
    await db.commit()
    await db.refresh(post, ["author", "likes", "saves", "comments"])

    return post_to_response(post, current_user.id)


@router.get("/posts/{post_id}", response_model=PostWithDetails)
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single post."""
    result = await db.execute(
        select(Post)
        .options(
            selectinload(Post.author),
            selectinload(Post.likes),
            selectinload(Post.saves),
            selectinload(Post.comments).selectinload(PostComment.author),
            selectinload(Post.comments).selectinload(PostComment.likes),
        )
        .where(Post.id == post_id)
    )
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Check visibility
    if post.visibility == PostVisibility.PRIVATE and post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if post.visibility == PostVisibility.PROJECT:
        user_project_ids = await get_user_project_ids(db, current_user.id)
        if post.project_id not in user_project_ids and post.author_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return post_to_response(post, current_user.id)


@router.put("/posts/{post_id}", response_model=PostWithDetails)
async def update_post(
    post_id: int,
    post_data: PostUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a post."""
    result = await db.execute(
        select(Post)
        .options(
            selectinload(Post.author),
            selectinload(Post.likes),
            selectinload(Post.saves),
            selectinload(Post.comments).selectinload(PostComment.author),
            selectinload(Post.comments).selectinload(PostComment.likes),
        )
        .where(Post.id == post_id)
    )
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if post.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to edit this post")

    update_data = post_data.model_dump(exclude_unset=True)
    if "media" in update_data and update_data["media"]:
        update_data["media"] = update_data["media"].model_dump() if hasattr(update_data["media"], "model_dump") else update_data["media"]

    for field, value in update_data.items():
        setattr(post, field, value)

    await db.commit()
    await db.refresh(post)

    return post_to_response(post, current_user.id)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a post."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if post.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this post")

    await db.delete(post)
    await db.commit()


# Like/Unlike posts
@router.post("/posts/{post_id}/like", response_model=LikeResponse)
async def toggle_post_like(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Like or unlike a post."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Check if already liked
    like_result = await db.execute(
        select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == current_user.id)
    )
    existing_like = like_result.scalar_one_or_none()

    if existing_like:
        # Unlike
        await db.delete(existing_like)
        post.likes_count = max(0, post.likes_count - 1)
        liked = False
    else:
        # Like
        like = PostLike(post_id=post_id, user_id=current_user.id)
        db.add(like)
        post.likes_count += 1
        liked = True

    await db.commit()
    await db.refresh(post)

    return LikeResponse(liked=liked, likes_count=post.likes_count)


# Save/Unsave posts
@router.post("/posts/{post_id}/save", response_model=SaveResponse)
async def toggle_post_save(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save or unsave a post."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Check if already saved
    save_result = await db.execute(
        select(PostSave).where(PostSave.post_id == post_id, PostSave.user_id == current_user.id)
    )
    existing_save = save_result.scalar_one_or_none()

    if existing_save:
        # Unsave
        await db.delete(existing_save)
        post.saves_count = max(0, post.saves_count - 1)
        saved = False
    else:
        # Save
        save = PostSave(post_id=post_id, user_id=current_user.id)
        db.add(save)
        post.saves_count += 1
        saved = True

    await db.commit()
    await db.refresh(post)

    return SaveResponse(saved=saved, saves_count=post.saves_count)


# Comments
@router.post("/posts/{post_id}/comments", response_model=PostCommentWithAuthor, status_code=status.HTTP_201_CREATED)
async def create_comment(
    post_id: int,
    comment_data: PostCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a comment to a post."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Verify parent comment exists if replying
    if comment_data.parent_id:
        parent_result = await db.execute(
            select(PostComment).where(
                PostComment.id == comment_data.parent_id,
                PostComment.post_id == post_id
            )
        )
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found")

    comment = PostComment(
        post_id=post_id,
        author_id=current_user.id,
        parent_id=comment_data.parent_id,
        content=comment_data.content,
    )

    db.add(comment)
    post.comments_count += 1

    await db.commit()
    await db.refresh(comment, ["author", "likes"])

    return PostCommentWithAuthor(
        id=comment.id,
        post_id=comment.post_id,
        author_id=comment.author_id,
        parent_id=comment.parent_id,
        content=comment.content,
        likes_count=comment.likes_count,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        author=UserResponse.model_validate(current_user),
        is_liked=False,
        replies=[],
    )


@router.get("/posts/{post_id}/comments", response_model=List[PostCommentWithAuthor])
async def get_comments(
    post_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get comments for a post."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Get top-level comments with their replies
    query = (
        select(PostComment)
        .options(
            selectinload(PostComment.author),
            selectinload(PostComment.likes),
            selectinload(PostComment.replies).selectinload(PostComment.author),
            selectinload(PostComment.replies).selectinload(PostComment.likes),
        )
        .where(PostComment.post_id == post_id, PostComment.parent_id == None)
        .order_by(PostComment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    comments = result.scalars().all()

    def build_comment_response(comment: PostComment) -> PostCommentWithAuthor:
        is_liked = any(like.user_id == current_user.id for like in comment.likes)
        replies = [build_comment_response(reply) for reply in comment.replies]

        return PostCommentWithAuthor(
            id=comment.id,
            post_id=comment.post_id,
            author_id=comment.author_id,
            parent_id=comment.parent_id,
            content=comment.content,
            likes_count=comment.likes_count,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            author=UserResponse.model_validate(comment.author),
            is_liked=is_liked,
            replies=replies,
        )

    return [build_comment_response(c) for c in comments]


@router.put("/posts/{post_id}/comments/{comment_id}", response_model=PostCommentResponse)
async def update_comment(
    post_id: int,
    comment_id: int,
    comment_data: PostCommentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a comment."""
    result = await db.execute(
        select(PostComment).where(
            PostComment.id == comment_id,
            PostComment.post_id == post_id
        )
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    if comment.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to edit this comment")

    comment.content = comment_data.content
    await db.commit()
    await db.refresh(comment)

    return comment


@router.delete("/posts/{post_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    post_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a comment."""
    result = await db.execute(
        select(PostComment).where(
            PostComment.id == comment_id,
            PostComment.post_id == post_id
        )
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    # Get post to update count
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one()

    if comment.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this comment")

    # Count replies being deleted too
    replies_count_result = await db.execute(
        select(func.count(PostComment.id)).where(PostComment.parent_id == comment_id)
    )
    replies_count = replies_count_result.scalar()

    post.comments_count = max(0, post.comments_count - 1 - replies_count)

    await db.delete(comment)
    await db.commit()


# Like/Unlike comments
@router.post("/posts/{post_id}/comments/{comment_id}/like", response_model=LikeResponse)
async def toggle_comment_like(
    post_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Like or unlike a comment."""
    result = await db.execute(
        select(PostComment).where(
            PostComment.id == comment_id,
            PostComment.post_id == post_id
        )
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    # Check if already liked
    like_result = await db.execute(
        select(CommentLike).where(
            CommentLike.comment_id == comment_id,
            CommentLike.user_id == current_user.id
        )
    )
    existing_like = like_result.scalar_one_or_none()

    if existing_like:
        # Unlike
        await db.delete(existing_like)
        comment.likes_count = max(0, comment.likes_count - 1)
        liked = False
    else:
        # Like
        like = CommentLike(comment_id=comment_id, user_id=current_user.id)
        db.add(like)
        comment.likes_count += 1
        liked = True

    await db.commit()
    await db.refresh(comment)

    return LikeResponse(liked=liked, likes_count=comment.likes_count)
