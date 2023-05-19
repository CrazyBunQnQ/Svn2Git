package org.crazybunqnq.svn2git.entity;

import lombok.Data;
import org.tmatesoft.svn.core.SVNLogEntry;
import org.tmatesoft.svn.core.SVNLogEntryPath;

import java.util.Date;
import java.util.LinkedHashMap;
import java.util.Map;

@Data
public class MergedSVNLogEntry {
    private long revision;
    private String author;
    private Date date;
    private String message;
    private Map<String, SVNLogEntryPath> changedPaths;

    public MergedSVNLogEntry(SVNLogEntry logEntry) {
        this.revision = logEntry.getRevision();
        this.author = logEntry.getAuthor();
        this.date = logEntry.getDate();
        this.message = logEntry.getMessage();
        this.changedPaths = new LinkedHashMap<>(logEntry.getChangedPaths());
    }
}

