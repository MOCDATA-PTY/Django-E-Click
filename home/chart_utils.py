"""
Utility functions for generating charts for email reports
"""
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from io import BytesIO


def generate_donut_chart(completion_rate, colors=None):
    """
    Generate a donut chart showing completion rate
    
    Args:
        completion_rate (float): Completion percentage (0-100)
        colors (tuple): Optional tuple of (completed_color, remaining_color)
        
    Returns:
        BytesIO: PNG image data
    """
    if colors is None:
        colors = ('#dc2626', '#e5e7eb')  # Red for completed, light gray for remaining
    
    remaining_rate = 100 - completion_rate
    
    # Create figure with smaller size
    fig, ax = plt.subplots(figsize=(3.5, 3.5))

    # Create pie chart
    wedges, texts = ax.pie(
        [completion_rate, remaining_rate],
        colors=colors,
        startangle=90,
        wedgeprops=dict(width=0.4, edgecolor='white', linewidth=2)
    )

    # Draw white circle in center for donut effect
    centre_circle = plt.Circle((0, 0), 0.60, fc='white')
    fig.gca().add_artist(centre_circle)

    # Add center text
    ax.text(0, 0, f'{completion_rate:.1f}%',
            ha='center', va='center',
            fontsize=28, weight='bold', color='#1f2937')

    ax.axis('equal')
    plt.tight_layout()

    # Save to BytesIO with lower DPI to reduce file size
    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png', dpi=80, bbox_inches='tight', facecolor='white')
    img_buffer.seek(0)
    plt.close()
    
    return img_buffer
