C     Stub for the platform-specific GETCL routine referenced by fp.for.
C     The original returned the command line; returning blanks makes fp
C     fall through to reading commands from standard input, which is how
C     this system drives it.
      SUBROUTINE GETCL(S)
      CHARACTER*80 S
      S=' '
      RETURN
      END
