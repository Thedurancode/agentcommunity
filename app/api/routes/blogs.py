import json
import re
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.blog import Blog, BlogStatus, BlogComment, BlogImage
from app.schemas.blog import (
    BlogCreate,
    BlogUpdate,
    BlogResponse,
    BlogWithAuthor,
    BlogWithDetails,
    BlogList,
    BlogFeed,
    BlogFeedItem,
    BlogAuthor,
    BlogCommentCreate,
    BlogCommentUpdate,
    BlogCommentResponse,
    BlogCommentWithAuthor,
    BlogCommentWithReplies,
    BlogCommentList,
    BlogCommentAuthor,
    BlogImageCreate,
    BlogImageResponse,
)
from app.api.deps import get_current_user


router = APIRouter(prefix="/blogs", tags=["blogs"])


def generate_slug(title: str) -> str:
    """Generate a URL-friendly slug from title."""
    slug = title.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = slug.strip('-')
    return slug


def parse_tags(tags_str: Optional[str]) -> List[str]:
    """Parse JSON tags string to list."""
    if not tags_str:
        return []
    try:
        return json.loads(tags_str)
    except (json.JSONDecodeError, TypeError):
        return []


def tags_to_json(tags: Optional[List[str]]) -> Optional[str]:
    """Convert tags list to JSON string."""
    if tags is None:
        return None
    return json.dumps(tags)


# ============== BLOG CRUD ENDPOINTS ==============

@router.post("", response_model=BlogWithAuthor, status_code=status.HTTP_201_CREATED)
async def create_blog(
    blog_data: BlogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new blog post."""
    # Generate slug if not provided
    slug = blog_data.slug if blog_data.slug else generate_slug(blog_data.title)

    # Check slug uniqueness
    existing = await db.execute(select(Blog).where(Blog.slug == slug))
    if existing.scalar_one_or_none():
        # Append timestamp to make unique
        slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

    blog = Blog(
        title=blog_data.title,
        slug=slug,
        excerpt=blog_data.excerpt,
        content=blog_data.content,
        cover_image=blog_data.cover_image,
        thumbnail=blog_data.thumbnail,
        status=blog_data.status,
        allow_comments=blog_data.allow_comments,
        meta_title=blog_data.meta_title,
        meta_description=blog_data.meta_description,
        tags=tags_to_json(blog_data.tags),
        category=blog_data.category,
        author_id=current_user.id,
        project_id=blog_data.project_id,
        published_at=datetime.utcnow() if blog_data.status == BlogStatus.PUBLISHED else None,
    )
    db.add(blog)
    await db.commit()
    await db.refresh(blog)

    # Load author relationship
    result = await db.execute(
        select(Blog)
        .options(selectinload(Blog.author))
        .where(Blog.id == blog.id)
    )
    blog = result.scalar_one()

    response = BlogWithAuthor.model_validate(blog)
    response.tags = parse_tags(blog.tags)
    response.author = BlogAuthor.model_validate(blog.author)
    return response


@router.get("", response_model=BlogList)
async def list_blogs(
    status_filter: Optional[BlogStatus] = Query(None, alias="status"),
    category: Optional[str] = Query(None),
    author_id: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List blogs (for authenticated users - includes drafts for own blogs)."""
    query = (
        select(Blog)
        .options(selectinload(Blog.author))
    )

    # Non-admin users can only see published blogs or their own
    if current_user.role.value != "admin":
        query = query.where(
            or_(
                Blog.status == BlogStatus.PUBLISHED,
                Blog.author_id == current_user.id
            )
        )

    if status_filter:
        query = query.where(Blog.status == status_filter)
    if category:
        query = query.where(Blog.category == category)
    if author_id:
        query = query.where(Blog.author_id == author_id)
    if project_id:
        query = query.where(Blog.project_id == project_id)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Get results
    query = query.order_by(Blog.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    blogs = result.scalars().all()

    blog_list = []
    for blog in blogs:
        item = BlogWithAuthor.model_validate(blog)
        item.tags = parse_tags(blog.tags)
        item.author = BlogAuthor.model_validate(blog.author)
        blog_list.append(item)

    return BlogList(blogs=blog_list, total=total)


@router.get("/feed", response_model=BlogFeed)
async def get_blog_feed(
    category: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    Public blog feed - only published blogs.
    No authentication required.
    """
    query = (
        select(Blog)
        .options(selectinload(Blog.author))
        .where(Blog.status == BlogStatus.PUBLISHED)
    )

    if category:
        query = query.where(Blog.category == category)
    if tag:
        query = query.where(func.lower(Blog.tags).contains(tag.lower()))
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Blog.title.ilike(search_term),
                Blog.excerpt.ilike(search_term),
                Blog.content.ilike(search_term),
            )
        )

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Get results
    query = query.order_by(Blog.published_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    blogs = result.scalars().all()

    feed_items = []
    for blog in blogs:
        item = BlogFeedItem(
            id=blog.id,
            title=blog.title,
            slug=blog.slug,
            excerpt=blog.excerpt,
            cover_image=blog.cover_image,
            thumbnail=blog.thumbnail,
            category=blog.category,
            tags=parse_tags(blog.tags),
            views_count=blog.views_count,
            likes_count=blog.likes_count,
            author=BlogAuthor.model_validate(blog.author),
            published_at=blog.published_at,
            created_at=blog.created_at,
        )
        feed_items.append(item)

    return BlogFeed(blogs=feed_items, total=total)


@router.get("/{blog_id_or_slug}", response_model=BlogWithDetails)
async def get_blog(
    blog_id_or_slug: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a blog by ID or slug. Public endpoint for published blogs."""
    # Try to parse as ID first
    try:
        blog_id = int(blog_id_or_slug)
        query = select(Blog).where(Blog.id == blog_id)
    except ValueError:
        query = select(Blog).where(Blog.slug == blog_id_or_slug)

    result = await db.execute(
        query.options(
            selectinload(Blog.author),
            selectinload(Blog.images),
        )
    )
    blog = result.scalar_one_or_none()

    if not blog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog not found"
        )

    # Only allow viewing if published (for public access)
    if blog.status != BlogStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog not found"
        )

    # Increment view count
    blog.views_count += 1
    await db.commit()

    # Get comments count
    comments_result = await db.execute(
        select(func.count(BlogComment.id)).where(
            BlogComment.blog_id == blog.id,
            BlogComment.is_approved == True
        )
    )
    comments_count = comments_result.scalar() or 0

    response = BlogWithDetails.model_validate(blog)
    response.tags = parse_tags(blog.tags)
    response.author = BlogAuthor.model_validate(blog.author)
    response.comments_count = comments_count
    return response


@router.patch("/{blog_id}", response_model=BlogWithAuthor)
async def update_blog(
    blog_id: int,
    blog_data: BlogUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a blog post (author or admin only)."""
    result = await db.execute(
        select(Blog)
        .options(selectinload(Blog.author))
        .where(Blog.id == blog_id)
    )
    blog = result.scalar_one_or_none()

    if not blog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog not found"
        )

    # Check ownership
    if blog.author_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this blog"
        )

    update_data = blog_data.model_dump(exclude_unset=True)

    # Handle tags
    if "tags" in update_data:
        update_data["tags"] = tags_to_json(update_data["tags"])

    # Handle status change to published
    if "status" in update_data and update_data["status"] == BlogStatus.PUBLISHED:
        if not blog.published_at:
            blog.published_at = datetime.utcnow()

    for field, value in update_data.items():
        setattr(blog, field, value)

    await db.commit()
    await db.refresh(blog)

    response = BlogWithAuthor.model_validate(blog)
    response.tags = parse_tags(blog.tags)
    response.author = BlogAuthor.model_validate(blog.author)
    return response


@router.delete("/{blog_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a blog post (author or admin only)."""
    result = await db.execute(select(Blog).where(Blog.id == blog_id))
    blog = result.scalar_one_or_none()

    if not blog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog not found"
        )

    if blog.author_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this blog"
        )

    await db.delete(blog)
    await db.commit()
    return None


# ============== BLOG IMAGES ==============

@router.post("/{blog_id}/images", response_model=BlogImageResponse, status_code=status.HTTP_201_CREATED)
async def add_blog_image(
    blog_id: int,
    image_data: BlogImageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add an image to a blog post."""
    result = await db.execute(select(Blog).where(Blog.id == blog_id))
    blog = result.scalar_one_or_none()

    if not blog:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")

    if blog.author_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    image = BlogImage(
        blog_id=blog_id,
        url=image_data.url,
        alt_text=image_data.alt_text,
        caption=image_data.caption,
        display_order=image_data.display_order,
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)
    return image


@router.delete("/{blog_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog_image(
    blog_id: int,
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a blog image."""
    result = await db.execute(select(Blog).where(Blog.id == blog_id))
    blog = result.scalar_one_or_none()

    if not blog:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")

    if blog.author_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    image_result = await db.execute(
        select(BlogImage).where(BlogImage.id == image_id, BlogImage.blog_id == blog_id)
    )
    image = image_result.scalar_one_or_none()

    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    await db.delete(image)
    await db.commit()
    return None


# ============== BLOG COMMENTS ==============

@router.get("/{blog_id}/comments", response_model=BlogCommentList)
async def list_comments(
    blog_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get comments for a blog post (public - only approved comments)."""
    # Verify blog exists and is published
    blog_result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.status == BlogStatus.PUBLISHED)
    )
    if not blog_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")

    # Get top-level comments (no parent)
    query = (
        select(BlogComment)
        .options(selectinload(BlogComment.author), selectinload(BlogComment.replies))
        .where(
            BlogComment.blog_id == blog_id,
            BlogComment.is_approved == True,
            BlogComment.parent_id == None
        )
        .order_by(BlogComment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    comments = result.scalars().all()

    # Count
    count_result = await db.execute(
        select(func.count(BlogComment.id)).where(
            BlogComment.blog_id == blog_id,
            BlogComment.is_approved == True,
            BlogComment.parent_id == None
        )
    )
    total = count_result.scalar() or 0

    comment_list = []
    for comment in comments:
        author_info = None
        if comment.author:
            author_info = BlogCommentAuthor(
                id=comment.author.id,
                username=comment.author.username,
                full_name=comment.author.full_name,
                profile_image=comment.author.profile_image,
            )
        elif comment.guest_name:
            author_info = BlogCommentAuthor(guest_name=comment.guest_name)

        # Get replies
        replies = []
        for reply in comment.replies:
            if reply.is_approved:
                reply_author = None
                if reply.author:
                    reply_author = BlogCommentAuthor(
                        id=reply.author.id,
                        username=reply.author.username,
                        full_name=reply.author.full_name,
                        profile_image=reply.author.profile_image,
                    )
                elif reply.guest_name:
                    reply_author = BlogCommentAuthor(guest_name=reply.guest_name)

                replies.append(BlogCommentWithAuthor(
                    **BlogCommentResponse.model_validate(reply).model_dump(),
                    author=reply_author
                ))

        comment_list.append(BlogCommentWithReplies(
            **BlogCommentResponse.model_validate(comment).model_dump(),
            author=author_info,
            replies=replies
        ))

    return BlogCommentList(comments=comment_list, total=total)


@router.post("/{blog_id}/comments", response_model=BlogCommentWithAuthor, status_code=status.HTTP_201_CREATED)
async def create_comment(
    blog_id: int,
    comment_data: BlogCommentCreate,
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a comment to a blog post."""
    # Verify blog exists and allows comments
    blog_result = await db.execute(
        select(Blog).where(
            Blog.id == blog_id,
            Blog.status == BlogStatus.PUBLISHED,
            Blog.allow_comments == True
        )
    )
    blog = blog_result.scalar_one_or_none()

    if not blog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog not found or comments disabled"
        )

    # Validate parent comment if provided
    if comment_data.parent_id:
        parent_result = await db.execute(
            select(BlogComment).where(
                BlogComment.id == comment_data.parent_id,
                BlogComment.blog_id == blog_id
            )
        )
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found")

    comment = BlogComment(
        blog_id=blog_id,
        content=comment_data.content,
        author_id=current_user.id if current_user else None,
        guest_name=comment_data.guest_name if not current_user else None,
        guest_email=comment_data.guest_email if not current_user else None,
        parent_id=comment_data.parent_id,
        is_approved=True,  # Auto-approve for now
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # Build response
    author_info = None
    if current_user:
        author_info = BlogCommentAuthor(
            id=current_user.id,
            username=current_user.username,
            full_name=current_user.full_name,
            profile_image=current_user.profile_image,
        )
    elif comment_data.guest_name:
        author_info = BlogCommentAuthor(guest_name=comment_data.guest_name)

    return BlogCommentWithAuthor(
        **BlogCommentResponse.model_validate(comment).model_dump(),
        author=author_info
    )


@router.patch("/{blog_id}/comments/{comment_id}", response_model=BlogCommentResponse)
async def update_comment(
    blog_id: int,
    comment_id: int,
    comment_data: BlogCommentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a comment (author or admin only)."""
    result = await db.execute(
        select(BlogComment).where(BlogComment.id == comment_id, BlogComment.blog_id == blog_id)
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    # Check authorization
    if comment.author_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    update_data = comment_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(comment, field, value)

    await db.commit()
    await db.refresh(comment)
    return comment


@router.delete("/{blog_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    blog_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a comment (author or admin only)."""
    result = await db.execute(
        select(BlogComment).where(BlogComment.id == comment_id, BlogComment.blog_id == blog_id)
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    if comment.author_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    await db.delete(comment)
    await db.commit()
    return None


# ============== LIKE BLOG ==============

@router.post("/{blog_id}/like", response_model=dict)
async def like_blog(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Like a blog post."""
    result = await db.execute(select(Blog).where(Blog.id == blog_id))
    blog = result.scalar_one_or_none()

    if not blog:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")

    blog.likes_count += 1
    await db.commit()

    return {"likes_count": blog.likes_count}
