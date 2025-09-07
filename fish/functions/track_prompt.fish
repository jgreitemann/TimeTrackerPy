function track_prompt
    set activities (track prompt -a 2> /dev/null)
    if test -n "$activities"
        echo -n " [$activities]"
    end
end
