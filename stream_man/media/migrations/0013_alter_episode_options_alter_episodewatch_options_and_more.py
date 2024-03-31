# Generated by Django 5.0 on 2024-01-01 22:01

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("media", "0012_alter_show_description"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="episode",
            options={"ordering": ("season", "sort_order")},
        ),
        migrations.AlterModelOptions(
            name="episodewatch",
            options={"ordering": ("watch_date",)},
        ),
        migrations.AlterModelOptions(
            name="season",
            options={"ordering": ("show", "sort_order")},
        ),
        migrations.AlterModelOptions(
            name="show",
            options={"ordering": ("name",)},
        ),
        migrations.RemoveConstraint(
            model_name="episode",
            name="Episode_season_episode_id",
        ),
        migrations.RemoveConstraint(
            model_name="episodewatch",
            name="EpisodeWatch_episode_watch_date",
        ),
        migrations.RemoveConstraint(
            model_name="season",
            name="Season_show_season_id",
        ),
        migrations.RemoveConstraint(
            model_name="show",
            name="Show_website_show_id",
        ),
        migrations.RemoveConstraint(
            model_name="updateque",
            name="UpdateQue_website",
        ),
        migrations.AlterField(
            model_name="episode",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.AlterField(
            model_name="episodewatch",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.AlterField(
            model_name="episodewatch",
            name="watch_date",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="season",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.AlterField(
            model_name="show",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.AlterField(
            model_name="updateque",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.AddConstraint(
            model_name="episode",
            constraint=models.UniqueConstraint(
                fields=("season", "episode_id"), name="UQ_Episode_season_episode_id"
            ),
        ),
        migrations.AddConstraint(
            model_name="season",
            constraint=models.UniqueConstraint(
                fields=("show", "season_id"), name="UQ_Season_show_season_id"
            ),
        ),
        migrations.AddConstraint(
            model_name="show",
            constraint=models.UniqueConstraint(
                fields=("website", "show_id"), name="UQ_Show_website_show_id"
            ),
        ),
        migrations.AddConstraint(
            model_name="updateque",
            constraint=models.UniqueConstraint(
                fields=("website",), name="UQ_UpdateQue_website"
            ),
        ),
    ]
